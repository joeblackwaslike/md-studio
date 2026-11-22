"""CLI wiring of the PDF reader, with a stub engine and no Docling or network."""

import sys
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from md_studio.cli import app, sources
from md_studio.extractors import Extractor
from md_studio.extractors.arxiv import ArxivClient, ArxivExtractor
from md_studio.readers import pdf

HTML = (
    '<html><body><h1 data-page="1">Intro</h1><p data-page="1">hello pdf</p>'
    '<h1 data-page="2">Next</h1><p data-page="2">more</p></body></html>'
)


class _Stub:
    def to_html(self, path: Path, images_dir: Path) -> str:
        return HTML


class _Arxiv:
    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/html/"):
            return httpx.Response(404)
        return httpx.Response(200, stream=httpx.ByteStream(b"%PDF-1.7"))


def _convert(*args: Path | str):
    return CliRunner().invoke(app, ["convert", *map(str, args)])


def test_cli_converts_a_pdf_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf, "DoclingEngine", _Stub)
    source = tmp_path / "x.pdf"
    source.write_bytes(b"%PDF")

    outcome = _convert(source)

    assert outcome.exit_code == 0, outcome.output
    text = (tmp_path / "x.md").read_text(encoding="utf-8")
    assert "hello pdf" in text
    assert "start_page: 2" in text


def test_missing_pdf_extra_is_a_one_line_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "md_studio.readers.pdf_docling", None)
    source = tmp_path / "x.pdf"
    source.write_bytes(b"%PDF")

    outcome = _convert(source)

    assert outcome.exit_code == 1
    assert "md-studio[pdf]" in outcome.output
    assert "Traceback" not in outcome.output
    assert len(outcome.output.strip().splitlines()) == 1


def test_cli_arxiv_id_falls_back_to_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = ArxivClient(0, transport=httpx.MockTransport(_Arxiv()), engine=_Stub())
    extractors: tuple[Extractor, ...] = (ArxivExtractor(client),)
    monkeypatch.setattr(sources, "build_extractors", lambda: extractors)
    dest = tmp_path / "p.md"

    outcome = _convert("2606.24937", "-o", dest)

    assert outcome.exit_code == 0, outcome.output
    assert "hello pdf" in dest.read_text(encoding="utf-8")
