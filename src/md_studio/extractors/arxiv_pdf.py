"""The arXiv PDF fallback, used when a paper has no HTML version."""

from dataclasses import replace
from http import HTTPStatus
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from md_studio.core.document import Document
from md_studio.core.exceptions import FetchStatusError, ReadError
from md_studio.extractors.arxiv_id import parse_arxiv_id
from md_studio.readers.pdf import read_pdf
from md_studio.readers.pdf_engines import PdfEngine
from md_studio.readers.source import load_source


def _read(raw: bytes, name: str, engine: PdfEngine | None) -> Document:
    with TemporaryDirectory() as folder:
        pdf = Path(folder) / name
        pdf.write_bytes(raw)
        return read_pdf(pdf, engine=engine)


def read_arxiv_pdf(
    source: str,
    transport: httpx.BaseTransport,
    engine: PdfEngine | None,
) -> Document:
    """Download ``https://arxiv.org/pdf/<id>`` for the paper in *source* and read it.

    Raises
    ------
    ReadError
        When arXiv has neither an HTML page nor a PDF for the paper, or the PDF cannot be read.
    """
    paper = parse_arxiv_id(source) or "this paper"
    url = f"https://arxiv.org/pdf/{paper}"
    try:
        loaded = load_source(url, transport)
    except FetchStatusError as error:
        if error.status != HTTPStatus.NOT_FOUND:
            raise
        raise ReadError(f"arXiv has no HTML or PDF version of {paper}") from None
    document = _read(loaded.raw, f"{paper.replace('/', '_')}.pdf", engine)
    return replace(document, metadata=replace(document.metadata, source_file=url))
