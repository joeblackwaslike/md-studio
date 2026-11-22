"""Tests for the HTML reader and the extractor protocol."""

import gzip
import itertools
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from lxml import etree

from md_studio.core.document import Document, SourceChapter
from md_studio.core.exceptions import ReadError
from md_studio.extractors import ExtractionPlan, resolve_extractor
from md_studio.readers.html import HtmlElement, read_html

PAGE = "<html><head><title>Hello</title></head><body><h1>Hi</h1><p>text</p></body></html>"
UTF8_PAGE = "<html><body><p>café — ok</p></body></html>"


def _fixed(body: bytes, status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, content=body))


def _write(tmp_path: Path, text: str = PAGE) -> Path:
    page = tmp_path / "page.html"
    page.write_text(text, encoding="utf-8")
    return page


def _boom(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down")


def _loop(request: httpx.Request) -> httpx.Response:
    return httpx.Response(302, headers={"location": "https://example.com/a"})


def _hop(request: httpx.Request) -> httpx.Response:
    return httpx.Response(302, headers={"location": "ftp://example.com/a"})


def _two_chapters(root: HtmlElement) -> list[SourceChapter]:  # type: ignore[no-any-unimported]
    return [SourceChapter("A", root), SourceChapter("B", root)]


def _failing(root: HtmlElement) -> list[SourceChapter]:  # type: ignore[no-any-unimported]
    raise ValueError("bad")


class _Endless(httpx.SyncByteStream):
    def __iter__(self) -> Iterator[bytes]:
        return itertools.repeat(b"x" * 10)


class _Drip(httpx.SyncByteStream):
    def __iter__(self) -> Iterator[bytes]:
        return itertools.islice(itertools.repeat(b"x"), 100)


class _Untouchable(httpx.SyncByteStream):
    def __iter__(self) -> Iterator[bytes]:
        raise AssertionError("body must not be read")


def _text(document: Document) -> str:
    return etree.tostring(document.chapters[0].element, method="text", encoding="unicode")  # type: ignore[call-overload,no-any-return]


def _small_cap(monkeypatch: pytest.MonkeyPatch, size: int = 100) -> None:
    monkeypatch.setattr("md_studio.readers.source.MAX_BYTES", size)


def test_local_html_becomes_single_chapter(tmp_path: Path) -> None:
    document = read_html(_write(tmp_path))

    assert isinstance(document, Document)
    assert document.metadata.title == "Hello"
    assert document.metadata.source_file == "page.html"
    assert [chapter.title for chapter in document.chapters] == ["Hello"]
    assert b"<p>text</p>" in etree.tostring(document.chapters[0].element)  # type: ignore[call-overload]


def test_url_source_is_fetched() -> None:
    document = read_html("https://example.com/a", transport=_fixed(PAGE.encode()))

    assert document.metadata.title == "Hello"
    assert document.metadata.source_file == "https://example.com/a"


def test_oversized_stream_without_content_length_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cap(monkeypatch)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=_Endless()))

    with pytest.raises(ReadError, match="exceeds"):
        read_html("https://example.com/big", transport=transport)


def test_oversized_local_file_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cap(monkeypatch, 10)

    with pytest.raises(ReadError, match="exceeds"):
        read_html(_write(tmp_path))


def test_non_http_scheme_rejected() -> None:
    with pytest.raises(ReadError, match="scheme"):
        read_html("ftp://example.com/a.html")


def test_http_error_status_becomes_read_error() -> None:
    with pytest.raises(ReadError, match="HTTP 404"):
        read_html("https://example.com/missing", transport=_fixed(b"no", status=404))


def test_transport_failure_becomes_read_error() -> None:
    with pytest.raises(ReadError, match="ConnectError"):
        read_html("https://example.com/a", transport=httpx.MockTransport(_boom))


def test_redirect_loop_becomes_read_error() -> None:
    with pytest.raises(ReadError, match="TooManyRedirects"):
        read_html("https://example.com/a", transport=httpx.MockTransport(_loop))


def test_redirect_to_other_scheme_becomes_read_error() -> None:
    with pytest.raises(ReadError, match="Could not fetch"):
        read_html("https://example.com/a", transport=httpx.MockTransport(_hop))


def test_missing_file_becomes_read_error(tmp_path: Path) -> None:
    with pytest.raises(ReadError, match="Could not read"):
        read_html(tmp_path / "nope.html")


def test_empty_document_becomes_read_error(tmp_path: Path) -> None:
    with pytest.raises(ReadError, match="parse"):
        read_html(_write(tmp_path, ""))


def test_splitter_chapters_are_used(tmp_path: Path) -> None:
    document = read_html(_write(tmp_path), splitter=_two_chapters)

    assert [chapter.title for chapter in document.chapters] == ["A", "B"]


def test_splitter_returning_nothing_becomes_read_error(tmp_path: Path) -> None:
    with pytest.raises(ReadError, match="splitter"):
        read_html(_write(tmp_path), splitter=lambda root: [])


def test_splitter_raising_becomes_read_error(tmp_path: Path) -> None:
    with pytest.raises(ReadError, match="splitter"):
        read_html(_write(tmp_path), splitter=_failing)


class _Extractor:
    def __init__(self, prefix: str, tag: str) -> None:
        self._prefix = prefix
        self._tag = tag

    def matches(self, source: str) -> bool:
        return source.startswith(self._prefix)

    def resolve(self, source: str) -> ExtractionPlan:
        return ExtractionPlan(
            reader=read_html,
            source=source,
            source_fixes=(self._tag,),
            metadata_overrides={"title": self._tag},
        )


def test_first_matching_extractor_wins() -> None:
    extractors = [
        _Extractor("https://other", "no"),
        _Extractor("https://a", "first"),
        _Extractor("https://a", "second"),
    ]

    plan = resolve_extractor("https://a/x", extractors)

    assert plan is not None
    assert plan.source_fixes == ("first",)


def test_no_matching_extractor_returns_none() -> None:
    assert resolve_extractor("https://a/x", [_Extractor("https://b", "no")]) is None


class _Chain:
    def __init__(self, hops: int) -> None:
        self._hops = hops

    def __call__(self, request: httpx.Request) -> httpx.Response:
        step = int(request.url.path.strip("/") or 0)
        if step >= self._hops:
            return httpx.Response(200, content=PAGE.encode())
        return httpx.Response(302, headers={"location": f"https://example.com/{step + 1}"})


def _chain(hops: int) -> httpx.MockTransport:
    return httpx.MockTransport(_Chain(hops))


def test_three_redirect_hops_succeed() -> None:
    document = read_html("https://example.com/0", transport=_chain(3))

    assert document.metadata.title == "Hello"


def test_four_redirect_hops_rejected() -> None:
    with pytest.raises(ReadError, match="TooManyRedirects"):
        read_html("https://example.com/0", transport=_chain(4))


def test_body_of_exactly_max_bytes_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cap(monkeypatch)
    body = b"<p>".ljust(100, b"x")

    assert read_html("https://example.com/a", transport=_fixed(body)).chapters


def test_body_one_byte_over_max_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cap(monkeypatch)

    with pytest.raises(ReadError, match="exceeds"):
        read_html("https://example.com/a", transport=_fixed(b"<p>".ljust(101, b"x")))


def test_gzip_bomb_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cap(monkeypatch, 1000)
    packed = gzip.compress(b"<p>".ljust(50_000, b"x"))
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            content=packed,
            headers={"content-encoding": "gzip"},
        ),
    )

    with pytest.raises(ReadError, match="exceeds"):
        read_html("https://example.com/a", transport=transport)


def test_slow_drip_of_tiny_pieces_hits_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = itertools.count(step=10)
    monkeypatch.setattr("md_studio.readers.source._clock", lambda: float(next(ticks)))
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=_Drip()))

    with pytest.raises(ReadError, match="deadline"):
        read_html("https://example.com/slow", transport=transport)


def test_declared_content_length_over_cap_rejected_without_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _small_cap(monkeypatch)
    response = httpx.Response(200, headers={"content-length": "101"}, stream=_Untouchable())
    transport = httpx.MockTransport(lambda request: response)

    with pytest.raises(ReadError, match="exceeds"):
        read_html("https://example.com/a", transport=transport)


def test_malformed_url_becomes_read_error() -> None:
    with pytest.raises(ReadError, match="Malformed"):
        read_html("http://[::1")


def test_nul_byte_path_becomes_read_error() -> None:
    with pytest.raises(ReadError, match="Could not read"):
        read_html("a\x00b.html")


def test_utf8_file_without_meta_is_decoded_as_utf8(tmp_path: Path) -> None:
    page = tmp_path / "u.html"
    page.write_bytes(UTF8_PAGE.encode())

    assert "café — ok" in _text(read_html(page))


def test_utf8_url_without_meta_is_decoded_as_utf8() -> None:
    document = read_html("https://example.com/u", transport=_fixed(UTF8_PAGE.encode()))

    assert "café — ok" in _text(document)


def test_meta_declared_latin1_is_honored() -> None:
    body = '<html><head><meta charset="iso-8859-1"></head><body><p>café</p></body></html>'
    document = read_html("https://example.com/l", transport=_fixed(body.encode("latin-1")))

    assert "café" in _text(document)


def test_content_type_charset_is_honored() -> None:
    body = "<html><body><p>café</p></body></html>".encode("latin-1")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            content=body,
            headers={"content-type": "text/html; charset=iso-8859-1"},
        ),
    )

    assert "café" in _text(read_html("https://example.com/l", transport=transport))


def test_utf8_bom_is_consumed(tmp_path: Path) -> None:
    page = tmp_path / "b.html"
    page.write_bytes(b"".join([b"\xef\xbb\xbf", UTF8_PAGE.encode()]))

    assert _text(read_html(page)).strip() == "café — ok"


def test_invalid_url_port_becomes_read_error() -> None:
    with pytest.raises(ReadError, match="Could not fetch"):
        read_html("http://a\u2603b.com:99999/")


def test_url_credentials_and_query_are_not_leaked() -> None:
    url = "https://user:pw@example.com/a.html?token=abc#frag"
    document = read_html(url, transport=_fixed(PAGE.encode()))

    assert document.metadata.source_file == "https://example.com/a.html"


def test_error_message_does_not_leak_credentials() -> None:
    url = "https://user:pw@example.com/a.html?token=abc"

    with pytest.raises(ReadError) as caught:
        read_html(url, transport=_fixed(b"no", status=500))

    assert "pw" not in str(caught.value)
    assert "token" not in str(caught.value)


def test_titleless_file_falls_back_to_stem(tmp_path: Path) -> None:
    page = tmp_path / "notes.html"
    page.write_text("<html><body><p>x</p></body></html>", encoding="utf-8")

    chapter = read_html(page).chapters[0]

    assert (chapter.title, chapter.title_is_fallback) == ("notes", True)


def test_fragment_without_body_still_yields_content(tmp_path: Path) -> None:
    page = tmp_path / "frag.html"
    page.write_text("<p>just a fragment</p>", encoding="utf-8")

    assert "just a fragment" in _text(read_html(page))


def test_svg_title_is_not_the_page_title(tmp_path: Path) -> None:
    page = tmp_path / "svg.html"
    page.write_text(
        "<html><body><svg><title>Pic</title></svg><p>x</p></body></html>", encoding="utf-8"
    )

    document = read_html(page)

    assert document.metadata.title == ""
    assert document.chapters[0].title == "svg"


def test_url_fallback_title_uses_last_path_segment() -> None:
    document = read_html("https://example.com/docs/guide.html", transport=_fixed(b"<p>x</p>"))

    assert document.chapters[0].title == "guide"


def test_url_fallback_title_uses_host_without_path() -> None:
    document = read_html("https://example.com/", transport=_fixed(b"<p>x</p>"))

    assert document.chapters[0].title == "example.com"


class _CountingExtractor(_Extractor):
    def __init__(self, prefix: str, tag: str) -> None:
        super().__init__(prefix, tag)
        self.resolved = 0

    def resolve(self, source: str) -> ExtractionPlan:
        self.resolved += 1
        return super().resolve(source)


def test_resolve_is_called_once_and_only_on_first_match() -> None:
    skipped = _CountingExtractor("https://other", "no")
    first = _CountingExtractor("https://a", "first")
    second = _CountingExtractor("https://a", "second")

    resolve_extractor("https://a/x", [skipped, first, second])

    assert (skipped.resolved, first.resolved, second.resolved) == (0, 1, 0)
