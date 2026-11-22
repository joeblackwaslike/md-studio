"""Headings: chapter titles, prefixed with their part."""

from collections.abc import Iterable

from md_studio.extractors.latexml_findings import Entry
from md_studio.extractors.latexml_text import plain_text
from md_studio.readers.html import HtmlElement

_SEPARATOR = " \u00b7 "
_CHAPTER = "ltx_chapter"
_PART_TAG = "ltx_tag"
_CLASS = "class"


def set_entry_titles(entries: Iterable[Entry]) -> None:
    """Give each entry its title, prefixed with its part (``Part II \u00b7 Chapter 12 ...``).

    Only chapters take the part prefix; the bibliography and appendices keep their own
    titles. The entry's own title heading is removed, since the chapter heading replaces it.
    Each part's label is read once, however many chapters it holds.
    """
    labels: dict[HtmlElement, str] = {}
    for entry in entries:
        heading = entry.title_element
        if heading is not None:
            entry.title = _prefixed(entry, plain_text(heading), labels)
            heading.drop_tree()


def _prefixed(entry: Entry, title: str, labels: dict[HtmlElement, str]) -> str:
    chapter = _CHAPTER in entry.element.get(_CLASS, "").split()
    prefix = _part_prefix(entry.part, labels) if chapter else ""
    return f"{prefix}{_SEPARATOR}{title}" if prefix and title else title


def _part_prefix(part: HtmlElement | None, labels: dict[HtmlElement, str]) -> str:
    if part is None:
        return ""
    if part not in labels:
        heading = part.find("h2")
        found = None if heading is None else next(filter(_is_label, heading), None)
        labels[part] = "" if found is None else plain_text(found)
    return labels[part]


def _is_label(element: HtmlElement) -> bool:
    return _PART_TAG in element.get(_CLASS, "").split()
