"""Footnote definitions, the :data:`Block` union, and the chapter container."""

from dataclasses import dataclass

from md_studio.core.ir.block import (
    CodeBlock,
    Heading,
    HorizontalRule,
    MathBlock,
    Paragraph,
)
from md_studio.core.ir.containers import BlockQuote, ListBlock
from md_studio.core.ir.table import Table


@dataclass(frozen=True, slots=True)
class FootnoteDef:
    """A footnote definition, rendered ``[^identifier]: ...`` at chapter end."""

    identifier: str
    children: tuple["Block", ...]


_TextBlock = Paragraph | Heading | CodeBlock | MathBlock | HorizontalRule
_ContainerBlock = BlockQuote | ListBlock | Table | FootnoteDef
Block = _TextBlock | _ContainerBlock


@dataclass(frozen=True, slots=True)
class ChapterIR:
    """One assembled chapter: a title, body blocks, and hoisted footnotes.

    ``title_is_fallback`` marks a title that is only a generated placeholder (the file
    stem or ``Chapter N``), which an extension may replace with a real heading. ``heading``,
    when set, is ready-made Markdown for the ``##`` line (a title with math in it), written
    as is; ``title`` stays the plain text used for the front matter and for matching.
    """

    title: str
    blocks: tuple[Block, ...]
    footnotes: tuple[FootnoteDef, ...] = ()
    title_is_fallback: bool = False
    heading: str = ""
