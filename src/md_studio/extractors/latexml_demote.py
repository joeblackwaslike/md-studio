"""Demote section headings under the chapter heading, by title class or else by tag."""

from collections.abc import Iterable
from types import MappingProxyType

from lxml import html as lxml_html

from md_studio.readers.html import HtmlElement

_DEPTH = MappingProxyType({
    "ltx_title_section": 1,
    "ltx_title_subsection": 2,
    "ltx_title_subsubsection": 3,
})
_LEVELS = MappingProxyType({"h4": "h2", "h5": "h3", "h6": "h4"})
_LEAD_IN = "ltx_title_paragraph"
_ARTICLE_SECTION_LEVEL = 2
_CLASS = "class"


def demote_headings(headings: Iterable[HtmlElement], entry_depth: int = 0) -> None:
    """Move section headings under the chapter heading; paragraph titles become bold lead-ins.

    A heading's level comes from its title class (section, subsection, subsubsection),
    relative to the entry: chapters hold sections (``h2``), while in a chapterless paper a
    section is the entry and its subsections are ``h2``. A heading with none of those
    classes (a theorem or acknowledgements title) is mapped by its tag: in a book ``h4``,
    ``h5`` and ``h6`` become ``h2``, ``h3`` and ``h4``; in a chapterless paper, whose
    headings sit one level higher, ``h3`` to ``h6`` drop by one (so ``h3`` is ``h2``) and
    ``h1``/``h2`` stay.
    """
    for heading in headings:
        classes = heading.get(_CLASS, "").split()
        if _LEAD_IN in classes:
            _lead_in(heading)
            continue
        heading.tag = _retag(heading.tag, classes, entry_depth)


def _named(level: int) -> str:
    return f"h{level}"


def _retag(tag: str, classes: list[str], entry_depth: int) -> str:
    depth = next((_DEPTH[name] for name in classes if name in _DEPTH), None)
    if depth is not None:
        return _named(max(depth - entry_depth + 1, 2))
    if entry_depth == 0:
        return _LEVELS.get(tag, tag)
    level = int(tag[1:])
    if level <= _ARTICLE_SECTION_LEVEL:
        return tag
    return _named(level - 1)


def _lead_in(heading: HtmlElement) -> None:
    strong = lxml_html.Element("strong")
    strong.text = heading.text
    heading.text = None
    strong.extend(list(heading))
    heading.append(strong)
    heading.tag = "p"
