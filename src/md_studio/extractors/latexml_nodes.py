"""Scan handlers for the nodes inside a chapter: sections, headings, math, figures, links."""

from md_studio.core.exceptions import ReadError
from md_studio.extractors.latexml_findings import Entry, Image
from md_studio.extractors.latexml_walk import Walk
from md_studio.readers.html import HtmlElement

SECTION_CLASSES = frozenset(("ltx_section", "ltx_subsection", "ltx_subsubsection"))


def section(walk: Walk, element: HtmlElement, classes: frozenset[str]) -> None:
    """Enter a section that has a heading of its own (paragraph sections do not)."""
    if classes & SECTION_CLASSES:
        walk.add_section(element)


def heading(walk: Walk, element: HtmlElement, classes: frozenset[str]) -> None:
    """Take a chapter's own title heading as its title; queue any other heading to demote."""
    if walk.title is not None:
        raise ReadError("LaTeXML page nests a heading inside a heading")
    walk.title = element
    entry = walk.entry
    if entry is not None and _is_title(entry, element):
        entry.title_element = element
    else:
        walk.found.headings.append(element)
        walk.found.outline.append(element)


def _is_title(entry: Entry, element: HtmlElement) -> bool:
    return entry.title_element is None and element.getparent() is entry.element


def math(walk: Walk, element: HtmlElement, classes: frozenset[str]) -> None:
    """Collect a ``<math>``, noting when it sits in a heading."""
    walk.found.maths.append(element)
    if walk.title is not None:
        walk.found.math_headings.add(walk.title)


def figure(walk: Walk, element: HtmlElement, classes: frozenset[str]) -> None:
    """Enter a figure, so its images can borrow its caption."""
    walk.stacks.figures.append(element)


def image(walk: Walk, element: HtmlElement, classes: frozenset[str]) -> None:
    """Collect an image with the figure it belongs to."""
    figures = walk.stacks.figures
    owner = figures[-1] if figures else None
    walk.found.images.append(Image(element, owner))


def link(walk: Walk, element: HtmlElement, classes: frozenset[str]) -> None:
    """Collect an anchor that has a target."""
    if element.get("href"):
        walk.found.links.append(element)
