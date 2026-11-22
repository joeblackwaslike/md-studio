"""Plain text of a LaTeXML subtree, reading math from its ``alttext``."""

from collections.abc import Callable
from dataclasses import dataclass

from lxml import etree

from md_studio.core.extract.tags import MATH_TAG, MATH_TEX_ATTR
from md_studio.core.render.math import inline_math
from md_studio.extractors.latexml_classes import classes_of
from md_studio.readers.html import HtmlElement

_ALTTEXT = "alttext"
_MATH_TAGS = frozenset(("math", MATH_TAG))
_HIDDEN = frozenset(("ltx_note", "noteref"))


def _text_content(math: HtmlElement) -> str:
    return " ".join("".join(math.itertext()).split())


def _tex(math: HtmlElement) -> str:
    return math.get(_ALTTEXT) or math.get(MATH_TEX_ATTR) or _text_content(math)


def _escape(text: str) -> str:
    return text.replace("$", r"\$")


def _delimited(math: HtmlElement) -> str:
    return inline_math(_tex(math))


@dataclass(frozen=True, slots=True)
class _Reader:
    """Reads a subtree's text, saying how math and ordinary text are written."""

    math: Callable[[HtmlElement], str]
    text: Callable[[str], str]

    def read(self, element: HtmlElement) -> str:
        parts: list[str] = []
        hidden = 0
        for event, node in etree.iterwalk(element, events=("start", "end", "comment", "pi")):
            hidden = self._advance(event, node, parts, hidden)
            if event != "start" and not hidden and node is not element:
                parts.append(self.text(node.tail or ""))
        return " ".join("".join(parts).split())

    def _advance(self, event: str, node: HtmlElement, parts: list[str], hidden: int) -> int:
        if event == "start":
            return self._enter(node, parts, hidden)
        return max(hidden - 1, 0) if event == "end" else hidden

    def _enter(self, node: HtmlElement, parts: list[str], hidden: int) -> int:
        if hidden:
            return hidden + 1
        if node.tag in _MATH_TAGS:
            parts.append(self.math(node))
            return 1
        if _HIDDEN & set(classes_of(node)):
            return 1
        parts.append(self.text(node.text or ""))
        return 0


def plain_text(element: HtmlElement) -> str:
    """Return the whitespace-normalised text of *element* in one pass.

    Math is replaced by its TeX (``alttext``, else its text), never by the MathML markup,
    footnotes and their markers are left out so a heading reads the same with or without
    them, and text after comments and processing instructions is kept. The tail of
    *element* itself is left out.
    """
    return _Reader(_tex, str).read(element)


def heading_markup(element: HtmlElement) -> str:
    """Return *element*'s text as Markdown for a heading: math as ``$tex$``, other ``$`` escaped.

    Math is normalised the way the renderer does (surrounding whitespace stripped, a lone
    ``$`` escaped), so the heading line reads the same as the inline math elsewhere.
    """
    return _Reader(_delimited, _escape).read(element)
