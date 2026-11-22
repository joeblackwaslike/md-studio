"""One pass over a LaTeXML page that finds everything the source fix rewrites.

The tree is walked once with start and end events (no descendant XPath), so cost is
linear in its size however it is shaped. Equations, listings and navigation are rewritten
whole, so nothing inside them is scanned, and chapters nested in chapters are not entries.
"""

from collections.abc import Callable
from types import MappingProxyType

from lxml import etree

from md_studio.core.exceptions import ReadError
from md_studio.extractors import latexml_boxes, latexml_nodes
from md_studio.extractors.latexml_findings import Findings
from md_studio.extractors.latexml_loose import LOOSE_CLASS, wrap_loose
from md_studio.extractors.latexml_walk import Walk
from md_studio.readers.html import HtmlElement

MAX_ELEMENTS = 1_000_000
_SECTION = "section"
_BOOK_ENTRIES = frozenset(("ltx_chapter", "ltx_appendix", "ltx_bibliography"))
_ARTICLE_ENTRIES = frozenset(("ltx_section", "ltx_appendix", "ltx_bibliography", LOOSE_CLASS))
_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
type _Rule = Callable[[Walk, HtmlElement, frozenset[str]], None]
_RULES: MappingProxyType[str, _Rule] = MappingProxyType({
    "nav": latexml_boxes.toc,
    "table": latexml_boxes.table,
    "div": latexml_boxes.box,
    "span": latexml_boxes.box,
    _SECTION: latexml_nodes.section,
    "math": latexml_nodes.math,
    "figure": latexml_nodes.figure,
    "img": latexml_nodes.image,
    "a": latexml_nodes.link,
    **dict.fromkeys(_HEADINGS, latexml_nodes.heading),
})


def check_size(root: HtmlElement, limit: int = MAX_ELEMENTS) -> None:
    """Raise :class:`ReadError` when *root* holds more than *limit* elements, counting in C."""
    if int(root.xpath("count(descendant-or-self::*)")) > limit:
        raise ReadError(f"LaTeXML page has too many elements (over {limit})")


def scan(root: HtmlElement, limit: int = MAX_ELEMENTS) -> Findings:
    """Scan *root* once and return what the source fix must rewrite.

    A page with chapters is split at its chapters, appendices and bibliography. A paper
    without chapters (an article) is split at its top-level sections instead, so the same
    rules apply to it.

    Raises
    ------
    ReadError
        When the tree has more than *limit* elements, or nests a heading in a heading.
    """
    book = _has_chapters(root)
    if not book:
        wrap_loose(root, _ARTICLE_ENTRIES)
    walk = Walk(limit, _BOOK_ENTRIES if book else _ARTICLE_ENTRIES)
    for event, element in etree.iterwalk(root, events=("start", "end")):
        if event == "end":
            walk.close(element)
        else:
            _start(walk, element)
    return walk.found


def _has_chapters(root: HtmlElement) -> bool:
    classes = (section.get("class", "") for section in root.iter(_SECTION))
    return any("ltx_chapter" in names.split() for names in classes)


def _start(walk: Walk, element: HtmlElement) -> None:
    walk.tick()
    if not isinstance(element.tag, str):
        return
    classes = frozenset(element.get("class", "").split())
    if walk.entry is None:
        _outside(walk, element, classes)
    elif walk.quiet is None:
        walk.note_id(element)
        rule = _RULES.get(element.tag)
        if rule is not None:
            rule(walk, element, classes)


def _outside(walk: Walk, element: HtmlElement, classes: frozenset[str]) -> None:
    if element.tag == _SECTION and "ltx_part" in classes:
        walk.stacks.parts.append(element)
    elif element.tag == _SECTION and classes & walk.entry_classes:
        walk.open_entry(element)
    else:
        _front(walk.found, element, classes)


def _front(found: Findings, element: HtmlElement, classes: frozenset[str]) -> None:
    if "ltx_titlepage" in classes and found.titlepage is None:
        found.titlepage = element
    elif "ltx_title_document" in classes and found.document_title is None:
        found.document_title = element
    else:
        _byline(found, element, classes)


def _byline(found: Findings, element: HtmlElement, classes: frozenset[str]) -> None:
    if "ltx_subtitle" in classes and found.subtitle is None:
        found.subtitle = element
    elif "ltx_authors" in classes and found.authors is None:
        found.authors = element
