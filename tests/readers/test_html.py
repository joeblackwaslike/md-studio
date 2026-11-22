"""Tests for the HTML reader and the extractor protocol."""

import contextlib
import gzip
import itertools
import threading
import time
import traceback
import tracemalloc
import zlib
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
    return httpx.MockTransport(lambda request: httpx.Response(status, stream=_Raw(body)))


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


class _Raw(httpx.SyncByteStream):
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __iter__(self) -> Iterator[bytes]:
        return iter([self._body])


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
    monkeypatch.setattr("md_studio.readers.limits.MAX_BYTES", size)


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
    with pytest.raises(ReadError, match="Too many redirects"):
        read_html("https://example.com/a", transport=httpx.MockTransport(_loop))


def test_redirect_to_other_scheme_becomes_read_error() -> None:
    with pytest.raises(ReadError, match="Unsupported redirect"):
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
            return httpx.Response(200, stream=_Raw(PAGE.encode()))
        return httpx.Response(302, headers={"location": f"https://example.com/{step + 1}"})


def _chain(hops: int) -> httpx.MockTransport:
    return httpx.MockTransport(_Chain(hops))


def test_three_redirect_hops_succeed() -> None:
    document = read_html("https://example.com/0", transport=_chain(3))

    assert document.metadata.title == "Hello"


def test_four_redirect_hops_rejected() -> None:
    with pytest.raises(ReadError, match="Too many redirects"):
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
            stream=_Raw(packed),
            headers={"content-encoding": "gzip"},
        ),
    )

    with pytest.raises(ReadError, match="exceeds"):
        read_html("https://example.com/a", transport=transport)


def test_slow_drip_of_tiny_pieces_hits_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = itertools.count(step=10)
    monkeypatch.setattr("md_studio.readers.deadline._clock", lambda: float(next(ticks)))
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
            stream=_Raw(body),
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


def _with_header_charset(body: bytes, charset: str) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            stream=_Raw(body),
            headers={"content-type": f"text/html; charset={charset}"},
        ),
    )


def test_decoy_meta_mentioning_charset_does_not_block_utf8() -> None:
    body = '<html><head><meta name="d" content="set charset here"></head><body><p>café — ok</p></body></html>'

    document = read_html("https://example.com/d", transport=_fixed(body.encode()))

    assert "café — ok" in _text(document)


def test_http_equiv_meta_charset_is_honored() -> None:
    body = (
        '<html><head><meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">'
        "</head><body><p>café</p></body></html>"
    )

    document = read_html("https://example.com/h", transport=_fixed(body.encode("latin-1")))

    assert "café" in _text(document)


@pytest.mark.parametrize(
    "charset", ["undefined", "unicode_escape", "raw_unicode_escape", "rot13", "idna"]
)
def test_non_text_charset_header_falls_back_to_utf8(charset: str) -> None:
    transport = _with_header_charset(UTF8_PAGE.encode(), charset)

    assert "café — ok" in _text(read_html("https://example.com/c", transport=transport))


def test_lone_surrogate_from_decoder_does_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("md_studio.readers.html.decode_html", lambda raw, charset: "\ud800<p>x</p>")

    document = read_html("https://example.com/s", transport=_fixed(b"<p>x</p>"))

    assert "x" in _text(document)


def test_resolve_is_called_once_and_only_on_first_match() -> None:
    skipped = _CountingExtractor("https://other", "no")
    first = _CountingExtractor("https://a", "first")
    second = _CountingExtractor("https://a", "second")

    resolve_extractor("https://a/x", [skipped, first, second])

    assert (skipped.resolved, first.resolved, second.resolved) == (0, 1, 0)


def _redirect_with_untouchable_body(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/start":
        return httpx.Response(
            302,
            headers={"location": "/final", "content-length": "1000"},
            stream=_Untouchable(),
        )
    return httpx.Response(200, stream=_Raw(PAGE.encode()))


def test_redirect_body_is_never_read(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cap(monkeypatch)
    transport = httpx.MockTransport(_redirect_with_untouchable_body)

    document = read_html("https://example.com/start", transport=transport)

    assert document.metadata.title == "Hello"


class _Relative:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(str(request.url))
        if request.url.path == "/docs/a":
            return httpx.Response(302, headers={"location": "../b/c.html?x=1"})
        return httpx.Response(200, stream=_Raw(PAGE.encode()))


def test_relative_location_resolves_against_current_url() -> None:
    relative = _Relative()

    read_html("https://example.com/docs/a", transport=httpx.MockTransport(relative))

    assert relative.seen == ["https://example.com/docs/a", "https://example.com/b/c.html?x=1"]


def _to_credentialed_ftp(request: httpx.Request) -> httpx.Response:
    return httpx.Response(302, headers={"location": "ftp://u:secret@example.com/a?k=v"})


def test_redirect_error_does_not_leak_target_credentials() -> None:
    with pytest.raises(ReadError) as caught:
        read_html("https://example.com/a", transport=httpx.MockTransport(_to_credentialed_ftp))

    assert "secret" not in str(caught.value)
    assert "k=v" not in str(caught.value)


class _Budget:
    def __init__(self, advance_first_hop: float) -> None:
        self.now = 0
        self.timeouts: list[float] = []
        self._advance = advance_first_hop

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.timeouts.append(request.extensions["timeout"]["read"])
        if request.url.path == "/0":
            self.now += self._advance
            return httpx.Response(302, headers={"location": "/1"})
        return httpx.Response(200, stream=_Raw(PAGE.encode()))

    def clock(self) -> float:
        return float(self.now)


class _LateFinal:
    def __init__(self, budget: _Budget) -> None:
        self._budget = budget

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self._budget.now += 31
        return httpx.Response(200, stream=_Raw(PAGE.encode()))


def test_each_hop_gets_only_the_remaining_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    budget = _Budget(20)
    monkeypatch.setattr("md_studio.readers.deadline._clock", budget.clock)

    read_html("https://example.com/0", transport=httpx.MockTransport(budget))

    assert budget.timeouts == [30.0, 10.0]


def test_expired_budget_before_next_hop_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    budget = _Budget(31)
    monkeypatch.setattr("md_studio.readers.deadline._clock", budget.clock)

    with pytest.raises(ReadError, match="deadline"):
        read_html("https://example.com/0", transport=httpx.MockTransport(budget))

    assert budget.timeouts == [30.0]


def test_deadline_passed_when_headers_arrive_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    budget = _Budget(0)
    monkeypatch.setattr("md_studio.readers.deadline._clock", budget.clock)

    with pytest.raises(ReadError, match="deadline"):
        read_html("https://example.com/1", transport=httpx.MockTransport(_LateFinal(budget)))


DECOYS = (
    '<meta data-charset="iso-8859-1">',
    '<meta name="description" content="Use charset=iso-8859-1">',
    '<!-- <meta charset="iso-8859-1"> -->',
    '<!--\n<meta charset="iso-8859-1">\n-->',
)


@pytest.mark.parametrize("decoy", DECOYS)
def test_decoy_charset_text_does_not_override_utf8(decoy: str) -> None:
    body = f"<html><head>{decoy}</head><body><p>café — ok</p></body></html>"

    document = read_html("https://example.com/d", transport=_fixed(body.encode()))

    assert "café — ok" in _text(document)


def test_latin1_label_decodes_as_cp1252_via_header() -> None:
    body = b"<html><body><p>\x93quoted\x94 \x80</p></body></html>"

    document = read_html(
        "https://example.com/w", transport=_with_header_charset(body, "iso-8859-1")
    )

    assert "\u201cquoted\u201d \u20ac" in _text(document)


def test_latin1_label_decodes_as_cp1252_via_meta() -> None:
    body = b'<html><head><meta charset="iso-8859-1"></head><body><p>\x93quoted\x94 \x80</p></body></html>'

    document = read_html("https://example.com/w", transport=_fixed(body))

    assert "\u201cquoted\u201d \u20ac" in _text(document)


CRED_URL = "https://user:s3cr3tpw@example.com/a.html?token=tok3n"


def _raise_with_url(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError(f"cannot reach {request.url}")


def _failure_trace(transport: httpx.MockTransport) -> str:
    try:
        read_html(CRED_URL, transport=transport)
    except ReadError as exc:
        return "".join(traceback.format_exception(exc))
    raise AssertionError("expected ReadError")


@pytest.mark.parametrize(
    "transport",
    [_fixed(b"no", status=500), httpx.MockTransport(_raise_with_url)],
)
def test_traceback_does_not_leak_url_secrets(transport: httpx.MockTransport) -> None:
    rendered = _failure_trace(transport)

    assert "s3cr3tpw" not in rendered
    assert "tok3n" not in rendered


def _encoded(body: bytes, encoding: str | None) -> httpx.MockTransport:
    headers = {} if encoding is None else {"content-encoding": encoding}
    return httpx.MockTransport(
        lambda request: httpx.Response(200, stream=_Raw(body), headers=headers)
    )


def test_single_gzip_body_is_decoded() -> None:
    document = read_html(
        "https://example.com/g", transport=_encoded(gzip.compress(PAGE.encode()), "gzip")
    )

    assert document.metadata.title == "Hello"


def test_deflate_zlib_and_raw_bodies_are_decoded() -> None:
    raw = zlib.compressobj(wbits=-15)
    raw_body = raw.compress(PAGE.encode()) + raw.flush()

    for body in (zlib.compress(PAGE.encode()), raw_body):
        document = read_html("https://example.com/z", transport=_encoded(body, "deflate"))
        assert document.metadata.title == "Hello"


def test_identity_encoding_is_accepted() -> None:
    document = read_html("https://example.com/i", transport=_encoded(PAGE.encode(), "identity"))

    assert document.metadata.title == "Hello"


@pytest.mark.parametrize("encoding", ["gzip, gzip", "br", "zstd", "compress", "gzip, br"])
def test_unsupported_or_chained_encodings_rejected(encoding: str) -> None:
    with pytest.raises(ReadError, match="content encoding"):
        read_html("https://example.com/x", transport=_encoded(gzip.compress(b"<p>x"), encoding))


def _peak_memory_reading(transport: httpx.MockTransport) -> int:
    tracemalloc.start()
    with contextlib.suppress(ReadError):
        read_html("https://example.com/b", transport=transport)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def test_gzip_bomb_never_materialises_past_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cap(monkeypatch, 1000)

    assert _peak_memory_reading(_encoded(gzip.compress(bytes(50_000_000)), "gzip")) < 5_000_000


class _Recorder:
    def __init__(self) -> None:
        self.accept_encoding: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.accept_encoding.append(request.headers["accept-encoding"])
        return httpx.Response(200, stream=_Raw(PAGE.encode()))


def test_accept_encoding_advertises_only_supported_codings() -> None:
    recorder = _Recorder()

    read_html("https://example.com/a", transport=httpx.MockTransport(recorder))

    assert recorder.accept_encoding == ["gzip, deflate"]


class _Pieces(httpx.SyncByteStream):
    def __init__(self, body: bytes, size: int, lead_empty: int = 0) -> None:
        self._parts = [
            *itertools.repeat(b"", lead_empty),
            *(body[at : at + size] for at in range(0, len(body), size)),
        ]

    def __iter__(self) -> Iterator[bytes]:
        return iter(self._parts)


def _delivered(body: bytes, encoding: str, size: int, lead_empty: int = 0) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            stream=_Pieces(body, size, lead_empty),
            headers={"content-encoding": encoding},
        ),
    )


def _raw_deflate(payload: bytes) -> bytes:
    compressor = zlib.compressobj(wbits=-15)
    return compressor.compress(payload) + compressor.flush()


@pytest.mark.parametrize("lead_empty", [0, 2])
@pytest.mark.parametrize(
    ("encoding", "body"),
    [
        ("deflate", zlib.compress(PAGE.encode())),
        ("deflate", _raw_deflate(PAGE.encode())),
        ("gzip", gzip.compress(PAGE.encode())),
    ],
)
def test_one_byte_pieces_decode_for_every_coding(
    encoding: str, body: bytes, lead_empty: int
) -> None:
    transport = _delivered(body, encoding, 1, lead_empty)

    assert read_html("https://example.com/p", transport=transport).metadata.title == "Hello"


def test_truncated_gzip_body_is_rejected() -> None:
    cut = gzip.compress(PAGE.encode())[:-10]

    with pytest.raises(ReadError, match="truncated"):
        read_html("https://example.com/t", transport=_delivered(cut, "gzip", 1000))


def test_truncated_deflate_body_is_rejected() -> None:
    cut = zlib.compress(PAGE.encode())[:-6]

    with pytest.raises(ReadError, match="truncated"):
        read_html("https://example.com/t", transport=_delivered(cut, "deflate", 1000))


def test_single_byte_compressed_body_is_rejected_as_truncated() -> None:
    with pytest.raises(ReadError, match="truncated"):
        read_html("https://example.com/t", transport=_delivered(b"\x1f", "gzip", 1))


def test_output_filling_the_step_boundary_is_not_lost() -> None:
    size = 65_536 * 2
    page = b"<p>".ljust(size, b"x")

    document = read_html(
        "https://example.com/s", transport=_delivered(gzip.compress(page), "gzip", 10**6)
    )

    assert len(_text(document).strip()) == size - len("<p>")


def test_trailing_bytes_after_the_stream_are_ignored() -> None:
    body = b"".join([gzip.compress(PAGE.encode()), b"garbage"])

    document = read_html("https://example.com/g", transport=_delivered(body, "gzip", 1000))

    assert document.metadata.title == "Hello"


def test_only_the_first_gzip_member_is_decoded() -> None:
    body = b"".join([gzip.compress(PAGE.encode()), gzip.compress(b"<title>Second</title>")])

    document = read_html("https://example.com/g", transport=_delivered(body, "gzip", 1000))

    assert document.metadata.title == "Hello"


class _Blocking(httpx.BaseTransport):
    def __init__(self) -> None:
        self.release = threading.Event()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.release.wait(5)
        raise httpx.ReadError("connection closed")

    def close(self) -> None:
        self.release.set()


def test_watchdog_cuts_off_a_blocked_read_at_the_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("md_studio.readers.deadline.DEADLINE_SECONDS", 0.2)
    started = time.monotonic()

    with pytest.raises(ReadError, match="total deadline"):
        read_html("https://example.com/block", transport=_Blocking())

    assert time.monotonic() - started < 3
