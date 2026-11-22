"""Tests for the PDF reader and the arXiv PDF fallback, using a stub engine."""

from pathlib import Path

import httpx
import pytest

from md_studio.core.convert import convert
from md_studio.core.exceptions import ReadError
from md_studio.extractors.arxiv import ArxivClient, ArxivExtractor
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
