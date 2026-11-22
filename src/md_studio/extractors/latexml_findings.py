"""What a scan of a LaTeXML page finds, kept in document order."""

from dataclasses import dataclass, field

from md_studio.readers.html import HtmlElement


@dataclass(slots=True)
class Entry:
    """One output chapter: a chapter, appendix or bibliography section."""

    element: HtmlElement
    part: HtmlElement | None
    title_element: HtmlElement | None = None
    title: str = ""


@dataclass(slots=True)
class Note:
    """A footnote span and the entry whose end collects its definition."""

    element: HtmlElement
    entry: Entry
    in_heading: bool = False


@dataclass(slots=True)
class Image:
    """An image and the figure that captions it, if any."""

    element: HtmlElement
    figure: HtmlElement | None


@dataclass(slots=True)
class Section:
    """A heading-bearing section; ``entry`` is set when it is a whole output chapter."""

    element: HtmlElement
    entry: Entry | None


@dataclass(slots=True)
class Findings:
    """Everything one scan found that the source fix rewrites."""

    entries: list[Entry] = field(default_factory=list)
    sections: dict[HtmlElement, Section] = field(default_factory=dict)
    outline: list["HtmlElement | Entry"] = field(default_factory=list)
    owners: dict[str, HtmlElement] = field(default_factory=dict)
    headings: list[HtmlElement] = field(default_factory=list)
    math_headings: set[HtmlElement] = field(default_factory=set)
    blocks: list[HtmlElement] = field(default_factory=list)
    maths: list[HtmlElement] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    links: list[HtmlElement] = field(default_factory=list)
    dropped: list[HtmlElement] = field(default_factory=list)
    entry_depth: int = 0
    titlepage: HtmlElement | None = None
    document_title: HtmlElement | None = None
    subtitle: HtmlElement | None = None
