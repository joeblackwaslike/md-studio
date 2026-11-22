"""Tests for the PDF reader and the arXiv PDF fallback, using a stub engine."""

from pathlib import Path

import httpx
import pytest

from md_studio.core.convert import convert
from md_studio.core.exceptions import ReadError
from md_studio.extractors.arxiv import ArxivClient, ArxivExtractor
from md_studio.readers import limits
from md_studio.readers.pdf import read_pdf

HTML = (
    "<html><body>"
    '<p data-page="1">preface</p>'
    '<h1 data-page="2">Intro</h1><p data-page="2">a</p><p data-page="3">b</p>'
    '<h2 data-page="3">Sub</h2><p data-page="4">c</p>'
    '<h1 data-page="5">Next</h1><p data-page="6">d</p>'
    '<md-math display="block" tex="x^2" data-page="6"></md-math>'
    "</body></html>"
)


class _Stub:
    def __init__(self, html: str = HTML) -> None:
        self.html = html

    def to_html(self, path: Path, images_dir: Path) -> str:
        return self.html


def _pdf(tmp_path: Path, name: str = "paper.pdf") -> Path:
    pdf = tmp_path / name
    pdf.write_bytes(b"%PDF")
    return pdf


def test_chapters_split_from_headings(tmp_path: Path) -> None:
    rendered = convert(read_pdf(_pdf(tmp_path), engine=_Stub()))

    assert [chapter.title for chapter in rendered.chapters] == ["paper", "Intro", "Next"]
    body = rendered.text.encode()
    slices = [
        body[chapter.start_byte : chapter.end_byte + 1].decode() for chapter in rendered.chapters
    ]
    assert all(piece.startswith("## ") for piece in slices)
    assert "### Sub" in slices[1]
    assert "$$" in slices[2]


def test_page_ranges_in_front_matter(tmp_path: Path) -> None:
    rendered = convert(read_pdf(_pdf(tmp_path), engine=_Stub()))

    assert [(chapter.start_page, chapter.end_page) for chapter in rendered.chapters] == [
        (1, 1),
        (2, 4),
        (5, 6),
    ]
    assert "    start_page: 2\n    end_page: 4\n" in rendered.front_matter


def test_headingless_pdf_is_one_chapter(tmp_path: Path) -> None:
    html = '<html><body><p data-page="1">x</p></body></html>'

    document = read_pdf(_pdf(tmp_path, "flat.pdf"), engine=_Stub(html))

    assert [chapter.title for chapter in document.chapters] == ["flat"]


def test_missing_pdf_is_a_read_error(tmp_path: Path) -> None:
    with pytest.raises(ReadError, match="Could not read"):
        read_pdf(tmp_path / "gone.pdf", engine=_Stub())


class _Arxiv:
    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.url.path.startswith("/html/"):
            return httpx.Response(404)
        return httpx.Response(200, stream=httpx.ByteStream(b"%PDF-1.7 fake"))


def test_arxiv_falls_back_to_pdf_on_html_404() -> None:  # noqa: WPS114
    server = _Arxiv()
    client = ArxivClient(
        0,
        transport=httpx.MockTransport(server),
        sleep=lambda seconds: None,
        engine=_Stub(),
    )
    plan = ArxivExtractor(client).resolve("2606.24937")

    document = plan.reader(plan.source)

    assert [request.url.path for request in server.seen] == ["/html/2606.24937", "/pdf/2606.24937"]
    assert "md-studio" in server.seen[1].headers["user-agent"]
    assert [chapter.title for chapter in document.chapters][1:] == ["Intro", "Next"]
    assert document.metadata.source_file == "https://arxiv.org/pdf/2606.24937"


def test_math_is_flagged_and_dollars_in_prose_are_escaped(tmp_path: Path) -> None:
    html = (
        '<html><body><h1 data-page="1">M</h1><p data-page="1">costs $5</p>'
        '<md-math display="block" tex="x^2" data-page="1"></md-math></body></html>'
    )

    document = read_pdf(_pdf(tmp_path), engine=_Stub(html))
    text = convert(document).text

    assert document.has_math
    assert "$$" in text
    assert r"\$5" in text


def test_empty_engine_output_is_a_read_error(tmp_path: Path) -> None:
    with pytest.raises(ReadError, match="no extractable text"):
        read_pdf(_pdf(tmp_path), engine=_Stub("<html><body></body></html>"))


def test_chapter_without_page_attributes_has_no_pages(tmp_path: Path) -> None:
    html = (
        '<html><body><h1>A</h1><p>x</p><h1 data-page="0">B</h1><p data-page="0">y</p></body></html>'
    )

    document = read_pdf(_pdf(tmp_path), engine=_Stub(html))

    assert [chapter.pages for chapter in document.chapters] == [None, None]
    assert "start_page" not in convert(document).front_matter


def test_oversize_file_is_rejected_before_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(limits, "MAX_BYTES", 3)

    with pytest.raises(ReadError, match="exceeds the size cap"):
        read_pdf(_pdf(tmp_path), engine=_Stub())


class _Routes:
    def __init__(self, html: int, pdf: httpx.Response | int) -> None:
        self.html = html
        self.pdf = pdf
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path.startswith("/html/"):
            return httpx.Response(self.html)
        if isinstance(self.pdf, int):
            return httpx.Response(self.pdf)
        return self.pdf


def _read(routes: _Routes, source: str) -> object:
    client = ArxivClient(0, transport=httpx.MockTransport(routes), sleep=lambda seconds: None)
    plan = ArxivExtractor(client).resolve(source)
    return plan.reader(plan.source)


def test_unparseable_html_url_cannot_fall_back(tmp_path: Path) -> None:
    client = ArxivClient(
        0, transport=httpx.MockTransport(_Routes(404, 404)), sleep=lambda seconds: None
    )

    with pytest.raises(ReadError, match="not an arXiv"):
        client.read("https://arxiv.org/html/foo")


def test_pdf_redirect_off_the_allowlist_is_a_read_error() -> None:
    redirect = httpx.Response(302, headers={"location": "https://evil.example/x.pdf"})
    routes = _Routes(404, redirect)

    with pytest.raises(ReadError, match="not allowed"):
        _read(routes, "2606.24937")


def test_pdf_server_error_after_missing_html_keeps_its_status() -> None:
    with pytest.raises(ReadError, match="HTTP 503"):
        _read(_Routes(404, 503), "2606.24937")


def test_html_server_error_does_not_fall_back() -> None:
    routes = _Routes(503, 200)

    with pytest.raises(ReadError, match="HTTP 503"):
        _read(routes, "2606.24937")

    assert routes.paths == ["/html/2606.24937"]


def test_old_style_id_falls_back_to_pdf() -> None:
    routes = _Routes(404, httpx.Response(200, stream=httpx.ByteStream(b"%PDF")))
    client = ArxivClient(
        0, transport=httpx.MockTransport(routes), sleep=lambda seconds: None, engine=_Stub()
    )
    plan = ArxivExtractor(client).resolve("hep-th/9901001")

    document = plan.reader(plan.source)

    assert routes.paths == ["/html/hep-th/9901001", "/pdf/hep-th/9901001"]
    assert document.metadata.source_file == "https://arxiv.org/pdf/hep-th/9901001"
