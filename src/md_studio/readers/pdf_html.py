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


class _Span(NamedTuple):
    first: int
    last: int


_NO_PAGE = _Span(0, 0)


class _Entry(NamedTuple):
    node: DocItem
    span: _Span
    kind: str | None


def _attr(span: _Span) -> str:
    first = f' data-page="{span.first}"' if span.first else ""
    spans = span.first and span.last > span.first
    return f'{first} data-page-end="{span.last}"' if spans else first


def _tag(name: str, span: _Span, body: str) -> str:
    return f"<{name}{_attr(span)}>{body}</{name}>"


def _kind(node: DocItem) -> str | None:
    if not isinstance(node, ListItem):
        return None
    tag = "ol" if node.enumerated else "ul"
    return ":".join((tag, node.parent.cref if node.parent else ""))


def _span_of(node: DocItem, previous: _Span) -> _Span:
    pages = [prov.page_no for prov in node.prov] or [previous.last]
    return _Span(pages[0], max(pages))


def _entries(document: DoclingDocument) -> Iterator[_Entry]:
    span = _NO_PAGE
    for node, _depth in document.iterate_items():
        if isinstance(node, DocItem) and node.label not in _RUNNING:
            span = _span_of(node, span)
            yield _Entry(node, span, _kind(node))


@singledispatch
def _block(node: DocItem, span: _Span, ctx: _Context) -> str:
    return ""


@_block.register
def _picture(node: PictureItem, span: _Span, ctx: _Context) -> str:
    caption = node.caption_text(ctx.document)
    return _tag("p", span, escape(caption)) if caption else ""


@_block.register
def _table(node: TableItem, span: _Span, ctx: _Context) -> str:
    marker = f"<table{_attr(span)}"
    return node.export_to_html(doc=ctx.document).replace("<table", marker, 1)


@_block.register
def _formula(node: FormulaItem, span: _Span, ctx: _Context) -> str:
    if not node.text.strip():
        return ""
    tex = escape(node.text, quote=True)
    return f'<md-math display="block" tex="{tex}"{_attr(span)}></md-math>'


def _level(node: SectionHeaderItem | TitleItem, ctx: _Context) -> int:
    if node.self_ref in ctx.front:
        return 1
    return heading_level(node.text, ctx.outline)


@_block.register
def _heading(node: SectionHeaderItem | TitleItem, span: _Span, ctx: _Context) -> str:
    name = f"h{_level(node, ctx)}"
    return _tag(name, span, escape(node.text))


@_block.register
def _code(node: CodeItem, span: _Span, ctx: _Context) -> str:
    return _tag("pre", span, _tag("code", _NO_PAGE, escape(node.text)))


@_block.register
def _paragraph(node: TextItem, span: _Span, ctx: _Context) -> str:
    return _tag("p", span, escape(node.text))


def _list_tag(entries: list[_Entry]) -> str:
    return (entries[0].kind or "ul").partition(":")[0]


def _listing(entries: list[_Entry]) -> str:
    body = "".join(map(_li, entries))
    return _tag(_list_tag(entries), _NO_PAGE, body)


def _li(entry: _Entry) -> str:
    return _tag("li", entry.span, escape(_text(entry)))


def _text(entry: _Entry) -> str:
    return entry.node.text if isinstance(entry.node, TextItem) else ""


def _render(pair: tuple[str | None, Iterable[_Entry]], ctx: _Context) -> str:
    kind, run = pair
    if kind is not None:
        return _listing(list(run))
    return "".join(_block(entry.node, entry.span, ctx) for entry in run)


def _entry_kind(entry: _Entry) -> str | None:
    return entry.kind


def _body(entries: Iterable[_Entry], ctx: _Context) -> str:
    return "".join(_render(pair, ctx) for pair in groupby(entries, _entry_kind))


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
