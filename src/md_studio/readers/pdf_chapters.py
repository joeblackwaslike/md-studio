"""Split a PDF engine's flat HTML into chapters at its top-level headings."""

import re
from collections.abc import Iterable

from lxml import html as lxml_html

from md_studio.core.document import SourceChapter
from md_studio.readers.html import HtmlElement

_HEADING = re.compile(r"h([1-6])")
_MAX_LEVEL = 6


def _level(element: HtmlElement) -> int | None:
    found = _HEADING.fullmatch(str(element.tag))
    return None if found is None else int(found.group(1))


def _pages(elements: Iterable[HtmlElement]) -> tuple[int, int] | None:
    numbers = [
        number
        for element in elements
        for node in element.iter()
        if (number := int(node.get("data-page", "0") or 0)) > 0
    ]
    return (min(numbers), max(numbers)) if numbers else None


def _demote(element: HtmlElement, top: int) -> None:
    level = _level(element)
    if level is not None:
        element.tag = f"h{min(level - top + 1, _MAX_LEVEL)}"


def _chapter(
    members: list[HtmlElement], title: str, top: int, *, led: bool, fallback: bool
) -> SourceChapter:
    pages = _pages(members)
    holder = lxml_html.Element("div")
    for member in members:
        holder.append(member)
        _demote(member, top)
    if led:
        holder.remove(members[0])
    return SourceChapter(title, holder, title_is_fallback=fallback, pages=pages)


def _heading_text(heading: HtmlElement) -> str:
    return " ".join(heading.text_content().split())


def _group_chapter(group: list[HtmlElement], stem: str, top: int) -> SourceChapter:
    led = _level(group[0]) == top
    title = _heading_text(group[0]) if led else ""
    return _chapter(group, title or stem, top, led=led, fallback=not title)


def _top_level(children: list[HtmlElement]) -> int:
    levels = [_level(child) for child in children]
    return min((level for level in levels if level), default=1)


def _groups(children: list[HtmlElement], top: int) -> list[list[HtmlElement]]:
    groups: list[list[HtmlElement]] = []
    for child in children:
        if _level(child) == top or not groups:
            groups.append([])
        groups[-1].append(child)
    return groups


def split_chapters(root: HtmlElement, stem: str) -> list[SourceChapter]:
    """Return one chapter per heading at the shallowest level present in *root*'s body.

    Content before the first such heading becomes a chapter titled *stem*. Deeper headings
    are demoted so the chapter's own heading is level 1. A body with no headings is a single
    chapter titled *stem*. Each chapter records the first and last ``data-page`` it carries.
    """
    body = root.find("body")
    children = list(root if body is None else body)
    top = _top_level(children)
    return [_group_chapter(group, stem, top) for group in _groups(children, top)]
