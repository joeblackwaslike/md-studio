"""Footnotes: each note span becomes a noteref anchor and a definition on its chapter."""

from collections.abc import Iterable

from lxml import html as lxml_html

from md_studio.extractors.latexml_classes import classes_of
from md_studio.extractors.latexml_findings import Note
from md_studio.readers.html import HtmlElement

_BODY_CLASS = "ltx_note_content"
_DROPPED = frozenset(("ltx_note_mark", "ltx_tag_note"))
_CLASS = "class"


def rewrite_footnotes(footnotes: Iterable[Note]) -> None:
    """Replace each footnote span by a ``noteref`` link and append its ``footnote`` block.

    The shapes are the ones the extractor already detects: an ``a.noteref`` pointing at
    ``#id`` and a ``div.footnote`` carrying that ``id``, appended to the end of the chapter
    so that it is a top-level definition there. Identifiers are always
    ``fn-N`` in document order, never taken from the page, so a hostile or repeated ``id``
    cannot inject Markdown or collide. A note inside a heading keeps its definition but
    leaves no marker in the heading, so the heading reads the same as its anchor.
    """
    for ordinal, footnote in enumerate(footnotes, start=1):
        identifier = f"fn-{ordinal}"
        if footnote.in_heading:
            footnote.element.drop_tree()
        else:
            _replace_span(footnote.element, identifier, ordinal)
        footnote.entry.element.append(_definition(footnote.element, identifier))


def _replace_span(span: HtmlElement, identifier: str, ordinal: int) -> None:
    reference = lxml_html.Element("a", href=f"#{identifier}")
    reference.set(_CLASS, "noteref")
    reference.text = str(ordinal)
    reference.tail = span.tail
    parent = span.getparent()
    if parent is not None:
        parent.replace(span, reference)


def _definition(span: HtmlElement, identifier: str) -> HtmlElement:
    box = lxml_html.Element("div")
    box.set("id", identifier)
    box.set(_CLASS, "footnote")
    paragraph = lxml_html.Element("p")
    box.append(paragraph)
    body = _body(span)
    if body is not None:
        paragraph.text = body.text
        for child in list(body):
            _move(paragraph, child)
    return box


def _keeps(child: HtmlElement) -> bool:
    if not isinstance(child.tag, str):
        return False
    return not _DROPPED & set(classes_of(child))


def _move(paragraph: HtmlElement, child: HtmlElement) -> None:
    if _keeps(child):
        paragraph.append(child)
    else:
        _add_text(paragraph, child.tail)


def _body(span: HtmlElement) -> HtmlElement | None:
    bodies = (inner for inner in span.iter("span") if _BODY_CLASS in classes_of(inner))
    return next(bodies, None)


def _add_text(paragraph: HtmlElement, text: str | None) -> None:
    if not text:
        return
    if len(paragraph):
        last = paragraph[-1]
        last.tail = (last.tail or "") + text
    else:
        paragraph.text = (paragraph.text or "") + text
