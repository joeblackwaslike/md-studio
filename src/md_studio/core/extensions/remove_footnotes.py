"""Extension: strip footnote references and definitions from chapters."""

from dataclasses import replace
from typing import ClassVar

from md_studio.core import ir, transform
from md_studio.core.extensions.base import ExtCtx, MarkdownExtension


def _drop_refs(node: ir.Inline) -> list[ir.Inline]:
    """Drop footnote references; keep everything else."""
    return [] if isinstance(node, ir.FootnoteRef) else [node]


class RemoveFootnotes(MarkdownExtension):
    """Remove footnote refs from the body and discard footnote definitions."""

    name: ClassVar[str] = "remove-footnotes"

    def transform_chapter(self, chapter: ir.ChapterIR, ctx: ExtCtx) -> ir.ChapterIR:
        """Return *chapter* with references stripped and no footnotes."""
        blocks = transform.map_inlines(chapter.blocks, _drop_refs)
        return replace(chapter, blocks=blocks, footnotes=())
