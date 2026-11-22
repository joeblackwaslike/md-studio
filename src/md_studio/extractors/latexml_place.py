"""Place a block element where an inline-embedded LaTeXML construct stood."""

from lxml import html as lxml_html

from md_studio.core.extract.tags import TRANSPARENT_TAGS
from md_studio.readers.html import HtmlElement

_CONTAINERS = TRANSPARENT_TAGS | {"li", "blockquote", "body"}
_CELLS = frozenset(("td", "th"))
_REACH = 64

type _Hits = list[tuple[HtmlElement, HtmlElement]]


class Placer:
    """Puts blocks where constructs stood, keeping reading order.

    A construct inside a paragraph splits the paragraph there, so the text before it, the
    block and the text after it come out in that order. Call :meth:`finish` once every
    block has been placed.
    """

    def __init__(self) -> None:
        """Start with nothing placed."""
        self._last: dict[HtmlElement, HtmlElement] = {}
        self._splits: dict[HtmlElement, dict[HtmlElement, _Hits]] = {}

    def place(self, old: HtmlElement, block: HtmlElement) -> None:
        """Put *block* where *old* was, or after it where it sits inline in a container.

        Blocks hoisted past the same container follow one another in the order placed. A
        paragraph is split once, in :meth:`finish`, however many blocks it holds.
        """
        parent = old.getparent()
        if parent is None:
            return
        anchor, below = _locate(old)
        if anchor is old:
            block.tail = old.tail
            parent.replace(old, block)
        elif anchor.tag == "p":
            self._defer(anchor, below, (old, block))
        else:
            previous = self._last.get(anchor)
            (anchor if previous is None else previous).addnext(block)
            self._last[anchor] = block
            old.drop_tree()

    def finish(self) -> None:
        """Split every paragraph that holds placed blocks, in one pass over its children."""
        for paragraph, points in self._splits.items():
            _split(paragraph, points)
        self._splits.clear()

    def _defer(
        self, paragraph: HtmlElement, below: HtmlElement, hit: tuple[HtmlElement, HtmlElement]
    ) -> None:
        points = self._splits.setdefault(paragraph, {})
        points.setdefault(below, []).append(hit)


def _locate(element: HtmlElement) -> tuple[HtmlElement, HtmlElement]:
    """Return the child of the nearest block container holding *element*, and its child on the path.

    The pair is *element* twice when it already sits in a container, or when a table cell
    (or the reach limit) is hit first and the block must stay inline.
    """
    below = element
    node = element
    for _ in range(_REACH):
        parent = node.getparent()
        if parent is None or parent.tag in _CELLS:
            return element, element
        if parent.tag in _CONTAINERS:
            return node, below
        below, node = node, parent
    return element, element


def _split(paragraph: HtmlElement, points: dict[HtmlElement, _Hits]) -> None:
    follow = _follow(paragraph, points)
    if follow:
        follow[-1].tail = paragraph.tail
        paragraph.tail = None
    after = paragraph
    for element in follow:
        after.addnext(element)
        after = element


def _follow(paragraph: HtmlElement, points: dict[HtmlElement, _Hits]) -> list[HtmlElement]:
    """Return the blocks and the paragraph segments that follow *paragraph*, in reading order."""
    follow: list[HtmlElement] = []
    segment = paragraph
    for child in list(paragraph):
        if segment is not paragraph:
            segment.append(child)
        hits = points.get(child)
        if hits is not None:
            added = _cut(child, hits)
            follow.extend(added)
            segment = added[-1]
    if follow and not len(segment) and not (segment.text or "").strip():
        follow.pop()
    return follow


def _cut(child: HtmlElement, hits: _Hits) -> list[HtmlElement]:
    """Return the blocks for *hits*, then the empty segment that continues after them."""
    segment = lxml_html.Element("p")
    segment.text = _remove(child, hits)
    return [*(block for _, block in hits), segment]


def _remove(child: HtmlElement, hits: _Hits) -> str | None:
    """Remove the constructs in *child* that became blocks; return the text after *child* if it went."""
    text = None
    for old, _ in hits:
        if old is child:
            text = child.tail
            child.tail = None
            child.getparent().remove(child)
        else:
            old.drop_tree()
    return text
