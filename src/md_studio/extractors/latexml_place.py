"""Place a block element where an inline-embedded LaTeXML construct stood."""

from md_studio.core.extract.tags import TRANSPARENT_TAGS
from md_studio.readers.html import HtmlElement

_CONTAINERS = TRANSPARENT_TAGS | {"li", "blockquote", "body"}
_CELLS = frozenset(("td", "th"))
_REACH = 64


class Placer:
    """Puts blocks where constructs stood, keeping document order among those hoisted together."""

    def __init__(self) -> None:
        """Start with nothing placed."""
        self._last: dict[HtmlElement, HtmlElement] = {}

    def place(self, old: HtmlElement, block: HtmlElement) -> None:
        """Put *block* where *old* was, or just after the container *old* sits inline in.

        Blocks hoisted past the same container follow one another in the order placed.
        """
        parent = old.getparent()
        if parent is None:
            return
        anchor = _container_child(old)
        if anchor is old:
            block.tail = old.tail
            parent.replace(old, block)
            return
        previous = self._last.get(anchor)
        (anchor if previous is None else previous).addnext(block)
        self._last[anchor] = block
        old.drop_tree()


def _container_child(element: HtmlElement) -> HtmlElement:
    """Return *element*, or the ancestor just under the nearest container that can hold a block."""
    node = element
    for _ in range(_REACH):
        parent = node.getparent()
        if parent is None or parent.tag in _CELLS:
            return element
        if parent.tag in _CONTAINERS:
            return node
        node = parent
    return element
