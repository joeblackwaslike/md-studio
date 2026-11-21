"""Intermediate representation for Markdown rendering.

The IR is a small recursive AST of immutable nodes produced by ``extract`` from
EPUB XHTML, transformed by the extension pipeline, and serialized by ``render``.
Frozen dataclasses are used (rather than Pydantic) because this is an internal
syntax tree, not validated boundary data: immutability makes extension
transforms functional and deterministic, and ``match`` statements stay clean.
"""
# flake8: noqa: WPS412 -- this package __init__ is a pure public-API re-export surface

from md_studio.core.ir.block import (
    CodeBlock,
    Heading,
    HorizontalRule,
    Paragraph,
)
from md_studio.core.ir.book import BookMeta
from md_studio.core.ir.containers import BlockQuote, ListBlock, ListItem
from md_studio.core.ir.document import Block, ChapterIR, FootnoteDef
from md_studio.core.ir.inline import (
    CodeSpan,
    Emphasis,
    LineBreak,
    Strong,
    Text,
)
from md_studio.core.ir.meta import Meta
from md_studio.core.ir.references import FootnoteRef, Image, Inline, Link
from md_studio.core.ir.table import Table, TableCell

__all__ = [
    "Block",
    "BlockQuote",
    "BookMeta",
    "ChapterIR",
    "CodeBlock",
    "CodeSpan",
    "Emphasis",
    "FootnoteDef",
    "FootnoteRef",
    "Heading",
    "HorizontalRule",
    "Image",
    "Inline",
    "LineBreak",
    "Link",
    "ListBlock",
    "ListItem",
    "Meta",
    "Paragraph",
    "Strong",
    "Table",
    "TableCell",
    "Text",
]
