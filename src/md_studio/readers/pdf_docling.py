"""Docling conversion of one PDF; imports Docling, so only load it when a PDF is read."""

from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from md_studio.readers.pdf_html import document_html
from md_studio.readers.pdf_outline import ensure_page_limit, outline_levels


def convert_pdf(path: Path, *, formulas: bool) -> str:
    """Convert *path* with Docling and return page-tagged HTML, outline levels on headings."""
    ensure_page_limit(path)
    options = PdfPipelineOptions(do_formula_enrichment=formulas)
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    document = converter.convert(path).document
    return document_html(document, outline_levels(path))
