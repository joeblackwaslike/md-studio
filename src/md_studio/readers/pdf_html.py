"""Render a Docling document as flat HTML whose blocks carry ``data-page`` attributes."""

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from functools import singledispatch
from html import escape
from itertools import groupby
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

from md_studio.readers.pdf_levels import heading_level, leading_unmatched

_RUNNING = frozenset((DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER))


@dataclass(frozen=True, slots=True)
class _Context:
    document: DoclingDocument
    outline: Mapping[str, int]
    front: frozenset[str] = frozenset()


class _Entry(NamedTuple):
    node: DocItem
    page: int


def _attr(page: int) -> str:
    return f' data-page="{page}"' if page else ""


def _tag(name: str, page: int, body: str) -> str:
    return f"<{name}{_attr(page)}>{body}</{name}>"


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
    caption = node.caption_text(ctx.document)
    return _tag("p", page, escape(caption)) if caption else ""


@_block.register
def _table(node: TableItem, page: int, ctx: _Context) -> str:
    marker = f"<table{_attr(page)}"
    return node.export_to_html(doc=ctx.document).replace("<table", marker, 1)


@_block.register
def _formula(node: FormulaItem, page: int, ctx: _Context) -> str:
    if not node.text.strip():
        return ""
    tex = escape(node.text, quote=True)
    return f'<md-math display="block" tex="{tex}"{_attr(page)}></md-math>'


def _level(node: SectionHeaderItem | TitleItem, ctx: _Context) -> int:
    if node.self_ref in ctx.front:
        return 1
    return heading_level(node.text, ctx.outline)


@_block.register
def _heading(node: SectionHeaderItem | TitleItem, page: int, ctx: _Context) -> str:
    name = f"h{_level(node, ctx)}"
    return _tag(name, page, escape(node.text))


@_block.register
def _code(node: CodeItem, page: int, ctx: _Context) -> str:
    return _tag("pre", page, _tag("code", 0, escape(node.text)))


@_block.register
def _paragraph(node: TextItem, page: int, ctx: _Context) -> str:
    return _tag("p", page, escape(node.text))


def _is_list(entry: _Entry) -> bool:
    return isinstance(entry.node, ListItem)


def _list_tag(entry: _Entry) -> str:
    return "ol" if isinstance(entry.node, ListItem) and entry.node.enumerated else "ul"


def _listing(entries: list[_Entry]) -> str:
    body = "".join(map(_li, entries))
    return _tag(_list_tag(entries[0]), 0, body)


def _li(entry: _Entry) -> str:
    return _tag("li", entry.page, escape(_text(entry)))


def _text(entry: _Entry) -> str:
    return entry.node.text if isinstance(entry.node, TextItem) else ""


def _render(pair: tuple[bool, Iterable[_Entry]], ctx: _Context) -> str:
    listed, run = pair
    if listed:
        return _listing(list(run))
    return "".join(_block(entry.node, entry.page, ctx) for entry in run)


def _body(entries: Iterable[_Entry], ctx: _Context) -> str:
    return "".join(_render(pair, ctx) for pair in groupby(entries, _is_list))


def _front(entries: list[_Entry], outline: Mapping[str, int]) -> frozenset[str]:
    headings = [
        entry.node for entry in entries if isinstance(entry.node, SectionHeaderItem | TitleItem)
    ]
    count = leading_unmatched([heading.text for heading in headings], outline)
    return frozenset(heading.self_ref for heading in headings[:count])


def document_html(document: DoclingDocument, outline: Mapping[str, int]) -> str:
    """Return *document* as HTML, dropping running headers and footers.

    Headings take their level from *outline*, except those before the first outline match,
    which are level 1. Text blocks keep their reading order, and list items are grouped into
    lists (ordered when numbered). Pictures keep only their caption text, and code blocks
    arrive from Docling without indentation.
    """
    entries = list(_entries(document))
    body = _body(entries, _Context(document, outline, _front(entries, outline)))
    return f"<html><body>{body}</body></html>"
