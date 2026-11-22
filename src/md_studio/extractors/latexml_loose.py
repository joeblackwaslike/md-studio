"""Content of a chapterless paper that sits outside its sections: abstract, keywords, notes."""

from lxml import html as lxml_html

from md_studio.extractors.latexml_classes import classes_of
from md_studio.readers.html import HtmlElement

LOOSE_CLASS = "ltx_loose"
TITLE_ATTR = "data-title"
_TITLES = (
    ("ltx_abstract", "Abstract"),
    ("ltx_keywords", "Keywords"),
    ("ltx_acknowledgements", "Acknowledgements"),
)
_NOT_CONTENT = frozenset(("ltx_titlepage", "ltx_pagination"))
_NAVIGATION = frozenset(("ltx_TOC", "ltx_page_navbar"))
_FRONT = "Front matter"
_LATER = "Additional material"


def wrap_loose(root: HtmlElement, entry_classes: frozenset[str]) -> None:
    """Wrap each run of visible content between a paper's sections in its own section.

    The abstract, keywords and any block between or after the sections would otherwise fall
    outside every chapter and be lost. Each run becomes a ``section.ltx_loose`` with a
    ``data-title`` (``Abstract``, ``Acknowledgements``, ``Front matter`` and so on) so the scan
    opens it as a chapter, in document order. Children are visited once.
    """
    first = next(
        (found for found in root.iter("section") if entry_classes & set(classes_of(found))),
        None,
    )
    container = None if first is None else first.getparent()
    if container is None:
        return
    run: list[HtmlElement] = []
    seen_entry = False
    for child in list(container):
        if not isinstance(child.tag, str):
            continue
        if _is_loose(child, entry_classes):
            run.append(child)
            continue
        seen_entry = seen_entry or bool(entry_classes & set(classes_of(child)))
        _flush(run, seen_entry=seen_entry)
        run = []
    _flush(run, seen_entry=True)


def _is_loose(child: HtmlElement, entry_classes: frozenset[str]) -> bool:
    classes = set(classes_of(child))
    if classes & (entry_classes | _NOT_CONTENT | _NAVIGATION):
        return False
    return _has_content(child)


def _has_content(element: HtmlElement) -> bool:
    return (
        bool("".join(element.itertext()).strip())
        or next(element.iter("img", "math"), None) is not None
    )


def _flush(run: list[HtmlElement], *, seen_entry: bool) -> None:
    if not run:
        return
    wrapper = lxml_html.Element("section")
    wrapper.set("class", LOOSE_CLASS)
    wrapper.set(TITLE_ATTR, _title(run, seen_entry=seen_entry))
    run[0].addprevious(wrapper)
    for element in run:
        wrapper.append(element)


def _title(run: list[HtmlElement], *, seen_entry: bool) -> str:
    names = [set(classes_of(element)) for element in run]
    for class_name, title in _TITLES:
        if any(class_name in found for found in names):
            return title
    return _LATER if seen_entry else _FRONT
