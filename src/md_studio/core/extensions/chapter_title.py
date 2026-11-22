"""Retitle chapters whose title is only the reader's file-name fallback."""

import re

from md_studio.core import ir
from md_studio.core.headings import text_of_inlines

_FILE_STEM_RE = re.compile(
    r"(?:xhtml|html|ch|chap|chapter|part|sec|section|split|content|text|file|item|page|id)"
    r"[-_.]?\d+(?:[-_.]\d+)*",
    re.IGNORECASE,
)


def retitle(chapter: ir.ChapterIR, blocks: tuple[ir.Block, ...]) -> str:
    """Return the chapter title, taking a file-stem-like one from a promoted first heading.

    The reader falls back to the file stem (``xhtml-0-2``, ``ch1``) when the source has
    no label, and to the first real ``<h1>``-``<h3>`` otherwise; this gives promoted
    CSS-styled headings the same treatment. Labelled titles are never replaced.
    """
    first = blocks[0] if blocks else None
    if not isinstance(first, ir.Heading) or first is chapter.blocks[0]:
        return chapter.title
    if not _FILE_STEM_RE.fullmatch(chapter.title):
        return chapter.title
    return text_of_inlines(first.children).strip() or chapter.title
