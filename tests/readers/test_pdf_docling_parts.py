"""Tests for the Docling-backed pieces; skipped when the pdf extra is not installed."""

from pathlib import Path

import pytest

from md_studio.core.exceptions import ReadError
from md_studio.readers import limits

pytest.importorskip("docling_core")
pytest.importorskip("pypdfium2")

from docling_core.types.doc.base import BoundingBox
from docling_core.types.doc.document import (
    DoclingDocument,
    ProvenanceItem,
    TableCell,
    TableData,
)
from docling_core.types.doc.labels import DocItemLabel

from md_studio.readers.pdf_html import document_html
from md_studio.readers.pdf_outline import ensure_page_limit, outline_levels

OUTLINE_PDF = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R /Outlines 5 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >> endobj
5 0 obj << /Type /Outlines /First 6 0 R /Last 7 0 R /Count 3 >> endobj
6 0 obj << /Title (Intro) /Parent 5 0 R /Next 7 0 R /First 8 0 R /Last 8 0 R /Count 1 /Dest [3 0 R /Fit] >> endobj
7 0 obj << /Title (Intro) /Parent 5 0 R /Prev 6 0 R /Dest [3 0 R /Fit] >> endobj
8 0 obj << /Title (Sub) /Parent 6 0 R /Dest [3 0 R /Fit] >> endobj
trailer << /Root 1 0 R /Size 9 >>
%%EOF
"""


def _prov(page: int) -> ProvenanceItem:
    return ProvenanceItem(page_no=page, bbox=BoundingBox(l=0, t=0, r=1, b=1), charspan=(0, 1))


def _table(doc: DoclingDocument) -> None:
    cell = TableCell(
        text="c",
        start_row_offset_idx=0,
        end_row_offset_idx=1,
        start_col_offset_idx=0,
        end_col_offset_idx=1,
    )
    doc.add_table(data=TableData(num_rows=1, num_cols=1, table_cells=[cell]), prov=_prov(3))


def _numbered(doc: DoclingDocument) -> None:
    group = doc.add_list_group()
    doc.add_list_item(text="one", enumerated=True, parent=group, prov=_prov(2))
    doc.add_list_item(text="two", enumerated=True, parent=group, prov=_prov(2))


def _document() -> DoclingDocument:
    doc = DoclingDocument(name="t")
    doc.add_text(label=DocItemLabel.PAGE_HEADER, text="Running head", prov=_prov(1))
    doc.add_heading(text="1 Intro", level=1, prov=_prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text="a < b", prov=_prov(1))
    _numbered(doc)
    doc.add_code(text="x = 1", prov=_prov(2))
    doc.add_formula(text="x^2", prov=_prov(3))
    doc.add_formula(text="", prov=_prov(3))
    _table(doc)
    doc.add_text(label=DocItemLabel.PAGE_FOOTER, text="Page 3", prov=_prov(3))
    return doc


@pytest.mark.parametrize(
    "fragment",
    [
        '<h1 data-page="1">1 Intro</h1>',
        '<p data-page="1">a &lt; b</p>',
        '<ol><li data-page="2">one</li><li data-page="2">two</li></ol>',
        '<pre data-page="2"><code>x = 1</code></pre>',
        '<md-math display="block" tex="x^2" data-page="3"></md-math>',
        '<table data-page="3">',
    ],
)
def test_document_html_tags_blocks_with_their_page(fragment: str) -> None:
    assert fragment in document_html(_document(), {"intro": 1})


@pytest.mark.parametrize("dropped", ["Running head", "Page 3"])
def test_document_html_drops_running_text(dropped: str) -> None:
    assert dropped not in document_html(_document(), {"intro": 1})


def test_empty_formula_placeholder_is_dropped() -> None:
    assert document_html(_document(), {"intro": 1}).count("<md-math") == 1


def test_front_headings_before_the_first_outline_match_are_level_one() -> None:
    doc = DoclingDocument(name="t")
    doc.add_heading(text="Paper Title", level=1, prov=_prov(1))
    doc.add_heading(text="1 Intro", level=1, prov=_prov(1))
    doc.add_heading(text="Unlisted", level=1, prov=_prov(1))

    html = document_html(doc, {"intro": 1, "sub": 2})

    assert '<h1 data-page="1">Paper Title</h1>' in html
    assert '<h3 data-page="1">Unlisted</h3>' in html


def test_outline_levels_read_a_generated_pdf_and_first_duplicate_wins(tmp_path: Path) -> None:
    pdf = tmp_path / "o.pdf"
    pdf.write_bytes(OUTLINE_PDF)

    assert outline_levels(pdf) == {"intro": 1, "sub": 2}


def test_pdf_without_an_outline_has_empty_levels(tmp_path: Path) -> None:
    pdf = tmp_path / "plain.pdf"
    pdf.write_bytes(OUTLINE_PDF.replace(b" /Outlines 5 0 R", b""))

    assert outline_levels(pdf) == {}


def test_page_limit_is_enforced_before_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "o.pdf"
    pdf.write_bytes(OUTLINE_PDF)
    ensure_page_limit(pdf)
    monkeypatch.setattr(limits, "MAX_PAGES", 0)

    with pytest.raises(ReadError, match="1 pages; the limit is 0"):
        ensure_page_limit(pdf)
