"""Scan handlers for constructs that are rewritten whole: contents, listings, equations, notes."""

from md_studio.extractors.latexml_findings import Note
from md_studio.extractors.latexml_walk import Walk
from md_studio.readers.html import HtmlElement

_EQUATIONS = frozenset(("ltx_equation", "ltx_equationgroup"))


def _equation(classes: frozenset[str]) -> bool:
    return "ltx_eqn_table" in classes and bool(classes & _EQUATIONS)


def toc(walk: Walk, element: HtmlElement, classes: frozenset[str]) -> None:
    """Drop a table of contents nested in a chapter."""
    if "ltx_TOC" in classes:
        walk.skip(element, walk.found.dropped)


def table(walk: Walk, element: HtmlElement, classes: frozenset[str]) -> None:
    """Collect an equation table, leaving ordinary tables alone."""
    if _equation(classes):
        walk.skip(element, walk.found.blocks)


def box(walk: Walk, element: HtmlElement, classes: frozenset[str]) -> None:
    """Collect a listing or inline equation, a list label, or a footnote."""
    if "ltx_listing" in classes or _equation(classes):
        walk.skip(element, walk.found.blocks)
    else:
        _label_or_note(walk, element, classes)


def _label_or_note(walk: Walk, element: HtmlElement, classes: frozenset[str]) -> None:
    if "ltx_tag_item" in classes:
        walk.found.dropped.append(element)
    elif "ltx_note" in classes and "ltx_role_footnote" in classes:
        _note(walk, element)


def _note(walk: Walk, element: HtmlElement) -> None:
    entry = walk.entry
    inside_heading = walk.title is not None
    if entry is not None:
        walk.found.notes.append(Note(element, entry, in_heading=inside_heading))
