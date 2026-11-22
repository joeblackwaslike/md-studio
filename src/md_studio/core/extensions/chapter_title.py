"""Retitle chapters whose title is only the reader's file-name fallback."""

from md_studio.core import ir
from md_studio.core.headings import text_of_inlines


def retitle(chapter: ir.ChapterIR, blocks: tuple[ir.Block, ...]) -> str:
    """Return the chapter title, taking a fallback one from a promoted first heading.

    The reader falls back to the file stem (``xhtml-0-2``) when the source has no label
    and no real ``<h1>``-``<h3>``, and records that in ``title_is_fallback``. Only such a
    title is replaced, by the text of the chapter's first block when that block was just
    promoted to a heading, which matches what a real first heading would have produced.
    An explicit label is never replaced, whatever it looks like.
    """
    first = blocks[0] if blocks else None
    if not chapter.title_is_fallback or not isinstance(first, ir.Heading):
        return chapter.title
    if first is chapter.blocks[0]:
        return chapter.title
    return text_of_inlines(first.children).strip() or chapter.title
