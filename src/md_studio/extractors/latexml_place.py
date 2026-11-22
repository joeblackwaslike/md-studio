"""Place a block element where an inline-embedded LaTeXML construct stood."""

from md_studio.core.extract.tags import TRANSPARENT_TAGS
from md_studio.extractors.latexml_split import Plan, split_paragraph
from md_studio.readers.html import HtmlElement

_CONTAINERS = TRANSPARENT_TAGS | {"li", "blockquote", "body"}
_CELLS = frozenset(("td", "th"))
_REACH = 64


class Placer:
    """Puts blocks where constructs stood, keeping reading order.

    A construct inside a paragraph splits the paragraph there, so the text before it, the
    block and the text after it come out in that order. Call :meth:`finish` once every
    block has been placed.
    """

    def __init__(self) -> None:
        """Start with nothing placed."""
        self._last: dict[HtmlElement, HtmlElement] = {}
        self._splits: dict[HtmlElement, Plan] = {}

    def place(self, old: HtmlElement, block: HtmlElement) -> None:
        """Put *block* where *old* was, or after it where it sits inline in a container.

        Blocks hoisted past the same container follow one another in the order placed. A
        paragraph is split once, in :meth:`finish`, however many blocks it holds.
        """
        parent = old.getparent()
        if parent is None:
            return
        anchor = _locate(old)
        if anchor is old:
            block.tail = old.tail
            parent.replace(old, block)
        elif anchor.tag == "p":
            self._defer(anchor, old, block)
        else:
            previous = self._last.get(anchor)
            (anchor if previous is None else previous).addnext(block)
            self._last[anchor] = block
            old.drop_tree()

    def finish(self) -> None:
        """Split every paragraph that holds placed blocks, in one pass over its children."""
        for paragraph, plan in self._splits.items():
            split_paragraph(paragraph, plan)
        self._splits.clear()

    def _defer(self, paragraph: HtmlElement, old: HtmlElement, block: HtmlElement) -> None:
        plan = self._splits.setdefault(paragraph, Plan())
        plan.blocks[old] = block
        wrapper = old.getparent()
        while wrapper is not paragraph and wrapper not in plan.holders:
            plan.holders.add(wrapper)
            wrapper = wrapper.getparent()


def _locate(element: HtmlElement) -> HtmlElement:
    """Return the child of the nearest block container that holds *element*.

    That is *element* itself when it already sits in a container, or when a table cell (or
    the reach limit) is hit first and the block must stay inline.
    """
    node = element
    for _ in range(_REACH):
        parent = node.getparent()
        if parent is None or parent.tag in _CELLS:
            return element
        if parent.tag in _CONTAINERS:
            return node
        node = parent
    return element
