"""Render a Docling document as flat HTML whose blocks carry ``data-page`` attributes."""

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from functools import singledispatch
from html import escape
from itertools import groupby
from pathlib import Path
from typing import NamedTuple

from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.items.code import CodeItem
from docling_core.types.doc.items.node import DocItem
from docling_core.types.doc.items.picture.picture import PictureItem
from docling_core.types.doc.items.table.table import TableItem
from docling_core.types.doc.items.text import (
    FormulaItem,
    ListItem,
    SectionHeaderItem,
    TextItem,
    TitleItem,
)
from docling_core.types.doc.labels import DocItemLabel

from md_studio.readers.pdf_levels import heading_level

_RUNNING = frozenset((DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER))


@dataclass(frozen=True, slots=True)
class _Context:
    document: DoclingDocument
    outline: Mapping[str, int]
    images: Path


class _Entry(NamedTuple):
    node: DocItem
    page: int


def _tag(name: str, page: int, body: str) -> str:
    attr = f' data-page="{page}"' if page else ""
    return f"<{name}{attr}>{body}</{name}>"


def _entries(document: DoclingDocument) -> Iterator[_Entry]:
    page = 0
    for node, _depth in document.iterate_items():
        if isinstance(node, DocItem) and node.label not in _RUNNING:
            page = node.prov[0].page_no if node.prov else page
            yield _Entry(node, page)


@singledispatch
def _block(node: DocItem, page: int, ctx: _Context) -> str:
    return ""


@_block.register
def _picture(node: PictureItem, page: int, ctx: _Context) -> str:
    image = node.get_image(ctx.document)
    if image is None:
        return ""
    number = len(list(ctx.images.iterdir())) + 1
    name = f"picture-{number}.png"
    image.save(ctx.images / name)
    alt = escape(node.caption_text(ctx.document), quote=True)
    return _tag("p", page, f'<img src="{name}" alt="{alt}">')


@_block.register
def _table(node: TableItem, page: int, ctx: _Context) -> str:
    marker = f'<table data-page="{page}"'
    return node.export_to_html(doc=ctx.document).replace("<table", marker, 1)


@_block.register
def _formula(node: FormulaItem, page: int, ctx: _Context) -> str:
    if not node.text.strip():
        return ""
    tex = escape(node.text, quote=True)
    attrs = f'display="block" tex="{tex}" data-page="{page}"'
    return f"<md-math {attrs}></md-math>"


@_block.register
def _heading(node: SectionHeaderItem | TitleItem, page: int, ctx: _Context) -> str:
    name = f"h{heading_level(node.text, ctx.outline)}"
    return _tag(name, page, escape(node.text))


@_block.register
def _code(node: CodeItem, page: int, ctx: _Context) -> str:
    return _tag("pre", page, _tag("code", 0, escape(node.text)))


@_block.register
def _paragraph(node: TextItem, page: int, ctx: _Context) -> str:
    return _tag("p", page, escape(node.text))


def _is_list(entry: _Entry) -> bool:
    return isinstance(entry.node, ListItem)


def _li(entry: _Entry) -> str:
    return _tag("li", entry.page, escape(_text(entry)))


def _text(entry: _Entry) -> str:
    return entry.node.text if isinstance(entry.node, TextItem) else ""


def _render(pair: tuple[bool, Iterable[_Entry]], ctx: _Context) -> str:
    listed, run = pair
    if listed:
        return _tag("ul", 0, "".join(map(_li, run)))
    return "".join(_block(entry.node, entry.page, ctx) for entry in run)


def _body(entries: Iterable[_Entry], ctx: _Context) -> str:
    return "".join(_render(pair, ctx) for pair in groupby(entries, _is_list))


def document_html(document: DoclingDocument, outline: Mapping[str, int], images_dir: Path) -> str:
    """Return *document* as HTML, dropping running headers and footers.

    Headings take their level from *outline*, text blocks keep their reading order, and list
    items are grouped into lists. Code blocks arrive from Docling without indentation.
    """
    body = _body(_entries(document), _Context(document, outline, images_dir))
    return f"<html><body>{body}</body></html>"
