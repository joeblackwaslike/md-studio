"""Small element helpers for rebuilding a paragraph."""

from lxml import html as lxml_html

from md_studio.readers.html import HtmlElement

_ID = "id"


def shell(node: HtmlElement) -> HtmlElement:
    """Return an empty element like *node*, without its ``id`` so ids stay unique."""
    attributes = dict(node.attrib)
    attributes.pop(_ID, None)
    return lxml_html.Element(node.tag, attributes)


def trim_end(target: HtmlElement) -> None:
    """Drop the whitespace a wrapper would otherwise end with, so ``*a *`` cannot happen."""
    if len(target):
        last = target[-1]
        last.tail = (last.tail or "").rstrip() or None
    else:
        target.text = (target.text or "").rstrip() or None


def is_empty(element: HtmlElement) -> bool:
    """Return whether *element* has no children and no text but whitespace."""
    return not len(element) and not (element.text or "").strip()
