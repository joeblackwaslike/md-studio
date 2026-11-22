"""Anchors for the headings a page's internal links can point at."""

from collections.abc import Mapping

from md_studio.extractors.latexml_findings import Findings, Section
from md_studio.extractors.latexml_slugs import github_slugs
from md_studio.extractors.latexml_text import plain_text
from md_studio.readers.html import HtmlElement

_HEADINGS = frozenset(("h1", "h2", "h3", "h4", "h5", "h6"))


def anchors(found: Findings) -> Mapping[str, str]:
    """Map each element id to the anchor of the heading it falls under, where it has one.

    Anchors follow the output headings in order (chapters, then sections), numbered the
    way GitHub numbers repeated headings. A heading holding math has no anchor, since its
    rendered text is not what the page says.
    """
    by_element = _slugs(found)
    return {
        identifier: by_element[owner]
        for identifier, owner in found.owners.items()
        if owner in by_element
    }


def _slugs(found: Findings) -> dict[HtmlElement, str]:
    usable = [section for section in found.sections if _usable(section, found)]
    slugs = github_slugs(_title(section) for section in usable)
    return {section.element: slug for section, slug in zip(usable, slugs, strict=True)}


def _usable(section: Section, found: Findings) -> bool:
    return bool(_title(section)) and not _has_math(section, found)


def _title(section: Section) -> str:
    if section.entry is not None:
        return section.entry.title
    own = _heading(section.element)
    return "" if own is None else plain_text(own)


def _heading(element: HtmlElement) -> HtmlElement | None:
    return next((child for child in element if child.tag in _HEADINGS), None)


def _has_math(section: Section, found: Findings) -> bool:
    entry = section.entry
    own = _heading(section.element) if entry is None else entry.title_element
    return own is not None and own in found.math_headings
