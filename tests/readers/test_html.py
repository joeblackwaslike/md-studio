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
from md_studio.readers.source import MAX_BYTES

PAGE = "<html><head><title>Hello</title></head><body><h1>Hi</h1><p>text</p></body></html>"
_MEGABYTE = 1_000_000


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
        for _ in range(MAX_BYTES // _MEGABYTE + 2):
            yield b"x" * _MEGABYTE


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


def test_oversized_response_rejected() -> None:
    body = b"x" * (MAX_BYTES + 1)

    with pytest.raises(ReadError, match="exceeds"):
        read_html("https://example.com/big", transport=_fixed(body))


def test_oversized_stream_without_content_length_rejected() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=_Endless()))

    with pytest.raises(ReadError, match="exceeds"):
        read_html("https://example.com/big", transport=transport)


def test_oversized_local_file_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("md_studio.readers.source.MAX_BYTES", 10)

    with pytest.raises(ReadError, match="exceeds"):
        read_html(_write(tmp_path))


def test_non_http_scheme_rejected() -> None:
    with pytest.raises(ReadError, match="scheme"):
        read_html("ftp://example.com/a.html")


def test_http_error_status_becomes_read_error() -> None:
    with pytest.raises(ReadError):
        read_html("https://example.com/missing", transport=_fixed(b"no", status=404))


def test_transport_failure_becomes_read_error() -> None:
    with pytest.raises(ReadError):
        read_html("https://example.com/a", transport=httpx.MockTransport(_boom))


def test_redirect_loop_becomes_read_error() -> None:
    with pytest.raises(ReadError):
        read_html("https://example.com/a", transport=httpx.MockTransport(_loop))


def test_redirect_to_other_scheme_becomes_read_error() -> None:
    with pytest.raises(ReadError):
        read_html("https://example.com/a", transport=httpx.MockTransport(_hop))


def test_missing_file_becomes_read_error(tmp_path: Path) -> None:
    with pytest.raises(ReadError):
        read_html(tmp_path / "nope.html")


def test_empty_document_becomes_read_error(tmp_path: Path) -> None:
    with pytest.raises(ReadError):
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
    with pytest.raises(ReadError):
        read_html("https://example.com/0", transport=_chain(4))


def test_body_of_exactly_max_bytes_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("md_studio.readers.source.MAX_BYTES", 100)
    body = b"<p>".ljust(100, b"x")

    assert read_html("https://example.com/a", transport=_fixed(body)).chapters


def test_body_one_byte_over_max_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("md_studio.readers.source.MAX_BYTES", 100)

    with pytest.raises(ReadError, match="exceeds"):
        read_html("https://example.com/a", transport=_fixed(b"<p>".ljust(101, b"x")))


def test_gzip_bomb_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("md_studio.readers.source.MAX_BYTES", 1000)
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


def test_slow_drip_hits_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = itertools.count(step=10)
    monkeypatch.setattr("md_studio.readers.source.time.monotonic", lambda: float(next(ticks)))
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=_Endless()))

    with pytest.raises(ReadError, match="deadline"):
        read_html("https://example.com/slow", transport=transport)


def test_malformed_url_becomes_read_error() -> None:
    with pytest.raises(ReadError):
        read_html("http://[::1")


def test_nul_byte_path_becomes_read_error() -> None:
    with pytest.raises(ReadError):
        read_html("a\x00b.html")
