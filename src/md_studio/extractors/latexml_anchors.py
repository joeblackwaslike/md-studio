"""Anchors for the headings a page's internal links can point at."""

from collections.abc import Mapping

from md_studio.core.headings import titles_match
from md_studio.extractors.latexml_classes import classes_of
from md_studio.extractors.latexml_findings import Entry, Findings, Section
from md_studio.extractors.latexml_slugs import github_slugs
from md_studio.extractors.latexml_text import plain_text
from md_studio.readers.html import HtmlElement

_HEADINGS = frozenset(("h1", "h2", "h3", "h4", "h5", "h6"))
_LEAD_IN = "ltx_title_paragraph"


def anchors(found: Findings) -> Mapping[str, str]:
    """Map each element id to the anchor of the heading it falls under, where it has one.

    Anchors are numbered the way GitHub numbers repeated headings, over every heading the
    output renders, in order: chapter titles and all headings, whether or not a link can
    point at them (a theorem title takes a number too). A heading holding math has no
    anchor, since its rendered text is not what the page says.
    """
    headings = _headings(found)
    slugs = dict(zip(headings, github_slugs(headings.values()), strict=True))
    return {
        identifier: slugs[target]
        for identifier, owner in found.owners.items()
        if (target := _target(found.sections.get(owner), found)) in slugs
    }


def _headings(found: Findings) -> dict[HtmlElement, str]:
    """Return the rendered heading texts in output order, keyed by heading (or entry) element."""
    texts: dict[HtmlElement, str] = {}
    current = ""
    for outlined in found.outline:
        if isinstance(outlined, Entry):
            current = outlined.title
            text, key = current, outlined.element
        else:
            text, key = _heading_text(outlined, current), outlined
        if text:
            texts[key] = text
    return texts


def _heading_text(heading: HtmlElement, entry_title: str) -> str:
    if _LEAD_IN in classes_of(heading):
        return ""
    text = plain_text(heading)
    return "" if titles_match(text, entry_title) else text


def _target(section: Section | None, found: Findings) -> HtmlElement | None:
    if section is None:
        return None
    if section.entry is not None:
        return None if section.entry.title_element in found.math_headings else section.element
    own = next((child for child in section.element if child.tag in _HEADINGS), None)
    return None if own in found.math_headings else own
