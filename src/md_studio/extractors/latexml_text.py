"""Plain text of a LaTeXML subtree, reading math from its ``alttext``."""

from lxml import etree

from md_studio.core.extract.tags import MATH_TAG, MATH_TEX_ATTR
from md_studio.extractors.latexml_classes import classes_of
from md_studio.readers.html import HtmlElement

_ALTTEXT = "alttext"
_MATH_TAGS = frozenset(("math", MATH_TAG))
_HIDDEN = frozenset(("ltx_note", "noteref"))


def _tex(math: HtmlElement) -> str:
    return math.get(_ALTTEXT) or math.get(MATH_TEX_ATTR) or ""


def _replacement(node: HtmlElement) -> str | None:
    """Return the text a node stands for with its subtree hidden, or ``None`` to read it."""
    if node.tag in _MATH_TAGS:
        return _tex(node)
    if _HIDDEN & set(classes_of(node)):
        return ""
    return None


def plain_text(element: HtmlElement) -> str:
    """Return the whitespace-normalised text of *element* in one pass.

    Math is replaced by its TeX (``alttext``), never by the MathML text, footnotes and their markers are
    left out so a heading reads the same with or without them, and text after comments and
    processing instructions is kept. The tail of *element* itself is left out.
    """
    parts: list[str] = []
    hidden = 0
    for event, node in etree.iterwalk(element, events=("start", "end", "comment", "pi")):
        if event == "start":
            hidden = _enter(node, parts, hidden)
        else:
            hidden = _leave(event, node, parts, hidden, element)
    return " ".join("".join(parts).split())


def _leave(event: str, node: HtmlElement, parts: list[str], hidden: int, root: HtmlElement) -> int:
    still = max(hidden - 1, 0) if event == "end" else hidden
    if not still and node is not root:
        parts.append(node.tail or "")
    return still


def _enter(node: HtmlElement, parts: list[str], hidden: int) -> int:
    if hidden:
        return hidden + 1
    replacement = _replacement(node)
    if replacement is None:
        parts.append(node.text or "")
        return 0
    parts.append(replacement)
    return 1
