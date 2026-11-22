"""Split a paragraph around the blocks that were embedded in it, closing and reopening wrappers.

A listing or equation can sit inside inline wrappers of a paragraph
(``<p>A<strong>B[listing]C</strong>D</p>``). The paragraph is rebuilt in one pass: the text
before the construct stays in a paragraph with its wrappers closed, the block follows, and the
rest continues in a new paragraph whose wrappers are cloned again, so ``C`` and ``D`` stay
after the block. Every original child is moved once, and a wrapper chain is cloned once per
construct (the chain is at most 64 deep, see ``latexml_place``).
"""

from collections.abc import Iterator
from dataclasses import dataclass, field

from md_studio.extractors.latexml_clone import is_empty, shell, trim_end
from md_studio.readers.html import HtmlElement


@dataclass(slots=True)
class Plan:
    """The constructs to cut out of one paragraph and the wrappers that lead to them."""

    blocks: dict[HtmlElement, HtmlElement] = field(default_factory=dict)
    holders: set[HtmlElement] = field(default_factory=set)


@dataclass(slots=True)
class _Level:
    node: HtmlElement
    children: Iterator[HtmlElement]

    @classmethod
    def open(cls, node: HtmlElement) -> "_Level":
        return cls(node, iter(list(node)))


@dataclass(slots=True)
class _Rebuild:
    paragraph: HtmlElement
    plan: Plan
    follow: list[HtmlElement] = field(default_factory=list)
    segments: set[HtmlElement] = field(default_factory=set)
    clones: list[HtmlElement] = field(default_factory=list)
    targets: list[HtmlElement] = field(default_factory=list)
    levels: list[_Level] = field(default_factory=list)

    def __post_init__(self) -> None:
        first = shell(self.paragraph)
        first.text = self.paragraph.text
        self.levels.append(_Level.open(self.paragraph))
        self.start_segment(first)

    def step(self, child: HtmlElement) -> None:
        block = self.plan.blocks.get(child)
        if block is None and child in self.plan.holders:
            self.enter(child)
        elif block is None:
            self.targets[-1].append(child)
        else:
            self.cut(block, child.tail)

    def cut(self, block: HtmlElement, text: str | None) -> None:
        trim_end(self.targets[-1])
        self.follow.append(block)
        self.start_segment(shell(self.paragraph))
        self.targets[-1].text = text.lstrip() if text else text

    def enter(self, wrapper: HtmlElement) -> None:
        clone = shell(wrapper)
        clone.text = wrapper.text
        self.clones.append(clone)
        self.targets[-1].append(clone)
        self.targets.append(clone)
        self.levels.append(_Level.open(wrapper))

    def leave(self) -> None:
        level = self.levels.pop()
        if self.levels:
            self.targets[-1].tail = level.node.tail
            self.targets.pop()

    def start_segment(self, segment: HtmlElement) -> None:
        self.segments.add(segment)
        self.follow.append(segment)
        self.targets = [segment]
        for level in self.levels[1:]:
            wrapper = shell(level.node)
            self.clones.append(wrapper)
            self.targets[-1].append(wrapper)
            self.targets.append(wrapper)


def split_paragraph(paragraph: HtmlElement, plan: Plan) -> None:
    """Replace *paragraph* by the paragraphs and blocks it splits into, in reading order."""
    rebuild = _Rebuild(paragraph, plan)
    while rebuild.levels:
        child = next(rebuild.levels[-1].children, None)
        if child is None:
            rebuild.leave()
        else:
            rebuild.step(child)
    _settle(paragraph, rebuild)


def _settle(paragraph: HtmlElement, rebuild: _Rebuild) -> None:
    """Drop empty wrappers and segments, then put what is left where *paragraph* was."""
    for clone in reversed(rebuild.clones):
        if is_empty(clone):
            clone.drop_tree()
    kept = [
        element
        for element in rebuild.follow
        if element not in rebuild.segments or not is_empty(element)
    ]
    if kept:
        kept[-1].tail = paragraph.tail
        paragraph.tail = None
    after = paragraph
    for element in kept:
        after.addnext(element)
        after = element
    paragraph.getparent().remove(paragraph)
