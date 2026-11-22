"""Where a scan currently is in the page: open parts, chapters, sections and figures."""

from dataclasses import dataclass, field

from md_studio.core.exceptions import ReadError
from md_studio.extractors.latexml_findings import Entry, Findings, Section
from md_studio.readers.html import HtmlElement


@dataclass(slots=True)
class Stacks:
    """The parts, sections and figures a scan is currently inside, innermost last."""

    parts: list[HtmlElement] = field(default_factory=list)
    sections: list[HtmlElement] = field(default_factory=list)
    figures: list[HtmlElement] = field(default_factory=list)


class Walk:
    """The scan's findings plus the stacks of elements it is currently inside.

    Elements are compared by identity: the stacks hold references, so lxml hands back
    the same Python object at the matching end event.
    """

    def __init__(self, limit: int, entry_classes: frozenset[str]) -> None:
        """Start an empty walk that fails after *limit* elements and opens *entry_classes*."""
        self.found = Findings(entry_depth=int("ltx_section" in entry_classes))
        self.entry_classes = entry_classes
        self.entry: Entry | None = None
        self.quiet: HtmlElement | None = None
        self.title: HtmlElement | None = None
        self.stacks = Stacks()
        self._limit = limit
        self._count = 0

    def tick(self) -> None:
        """Count one element, raising :class:`ReadError` past the limit."""
        self._count += 1
        if self._count > self._limit:
            raise ReadError(f"LaTeXML page has too many elements (over {self._limit})")

    def open_entry(self, element: HtmlElement) -> None:
        """Enter a chapter, appendix or bibliography; chapters nested in it are not entries."""
        part = self.stacks.parts[-1] if self.stacks.parts else None
        self.entry = Entry(element, part)
        self.found.entries.append(self.entry)
        self.found.outline.append(self.entry)
        self.stacks.sections.append(element)
        self.found.sections[element] = Section(element, self.entry)
        self.note_id(element)

    def add_section(self, element: HtmlElement) -> None:
        """Enter a section whose heading can be linked to."""
        self.stacks.sections.append(element)
        self.found.sections[element] = Section(element, None)
        self.note_id(element)

    def note_id(self, element: HtmlElement) -> None:
        """Record which section an element with an ``id`` falls under."""
        identifier = element.get("id")
        if identifier and self.stacks.sections:
            self.found.owners[identifier] = self.stacks.sections[-1]

    def skip(self, element: HtmlElement, bucket: list[HtmlElement]) -> None:
        """Collect *element* and ignore everything inside it, since it is rewritten whole."""
        bucket.append(element)
        self.quiet = element

    def close(self, element: HtmlElement) -> None:
        """Leave *element*, popping whatever it opened."""
        if self.quiet is element:
            self.quiet = None
        if self.title is element:
            self.title = None
        if self.entry is not None and self.entry.element is element:
            self.entry = None
        for stack in (self.stacks.figures, self.stacks.sections, self.stacks.parts):
            if stack and stack[-1] is element:
                stack.pop()
