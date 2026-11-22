"""Convert EPUB inline elements (and their text/tails) into the inline IR.

The most error-prone part is lxml's text model: text between sibling elements
lives on the *previous* element's ``.tail`` (not as a separate node), so every
collector reads ``el.text`` and then, for each child, the child's converted
content *and* its ``.tail``.
"""

from types import MappingProxyType

from lxml import html

from md_studio.core import ir
from md_studio.core.extract import anchors
from md_studio.core.extract.normalize import normalize_inlines
from md_studio.core.extract.tags import (
    EMPHASIS_TAGS,
    MATH_TAG,
    MATH_TEX_ATTR,
    STRIKE_TAGS,
    STRONG_TAGS,
    localname,
)

_FORMATTING: MappingProxyType[str, type[ir.Emphasis | ir.Strong | ir.Strikethrough]] = (
    MappingProxyType({
        **dict.fromkeys(EMPHASIS_TAGS, ir.Emphasis),
        **dict.fromkeys(STRONG_TAGS, ir.Strong),
        **dict.fromkeys(STRIKE_TAGS, ir.Strikethrough),
    })
)


def collect_inline(element: html.HtmlElement) -> list[ir.Inline]:  # type: ignore[no-any-unimported]
    """Collect the inline content of *element* (its text + children + tails)."""
    nodes: list[ir.Inline] = []
    if element.text:
        nodes.append(ir.Text(element.text))
    for child in element:
        nodes.extend(convert_inline_child(child))
        if child.tail:
            nodes.append(ir.Text(child.tail))
    return nodes


def normalized_children(element: html.HtmlElement) -> tuple[ir.Inline, ...]:  # type: ignore[no-any-unimported]
    """Return *element*'s normalized inline children as a tuple."""
    return tuple(normalize_inlines(collect_inline(element)))


def _convert_image(child: html.HtmlElement) -> ir.Image:  # type: ignore[no-any-unimported]
    """Convert an ``<img>`` element into an image node."""
    alt = child.get("alt", "")
    src = child.get("src", "")
    return ir.Image(alt=alt, src=src)


def _convert_simple(child: html.HtmlElement, tag: str) -> list[ir.Inline]:  # type: ignore[no-any-unimported]
    """Convert code/break/image inline tags, else pass through children."""
    if tag == "code":
        return [ir.CodeSpan("".join(child.itertext()))]
    if tag == "br":
        return [ir.LineBreak()]
    if tag == "img":
        return [_convert_image(child)]
    if tag == MATH_TAG:
        return [ir.Math(child.get(MATH_TEX_ATTR, ""))]
    return normalize_inlines(collect_inline(child))


def convert_inline_child(child: html.HtmlElement) -> list[ir.Inline]:  # type: ignore[no-any-unimported]
    """Convert a single inline child element into IR inline nodes."""
    if not isinstance(child.tag, str):
        return []
    tag = localname(child)
    formatting = _FORMATTING.get(tag)
    if formatting is not None:
        return [formatting(normalized_children(child))]
    if tag == "a":
        return anchors.convert_anchor(child)
    if tag in {"sup", "sub"}:
        return anchors.convert_sup_sub(child)
    return _convert_simple(child, tag)
