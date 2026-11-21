"""Extension: promote font-size/styled paragraphs to real headings.

Some books encode structure with styled paragraphs instead of ``<h1>``-``<h6>``.
This promotes those to real headings so the document gets a usable outline. When
the source supplies a stylesheet, classes it styles as headings (see
:mod:`md_studio.core.extensions.css_headings`) decide the level; otherwise an inline
``font-size`` or a heading-ish class name does. Heading levels here are pre-shift;
the renderer demotes them by one under the chapter ``##`` heading. Every promotion
is logged to ``ctx.audit``. A chapter whose title is a bare file stem (the reader's fallback
when the source has no label, e.g. ``xhtml-0-2`` or ``ch1``) takes the text of its first block when that block is promoted,
matching the usual first-heading title fallback for real ``<h1>``-``<h3>`` headings.
"""

import re
from collections.abc import Mapping
from typing import ClassVar

from md_studio.core import ir
from md_studio.core.extensions.audit import AuditLog, PromotionRecord
from md_studio.core.extensions.base import ExtCtx, MarkdownExtension
from md_studio.core.extensions.css_headings import classify
from md_studio.core.headings import text_of_inlines

_FONT_SIZE_RE = re.compile(
    r"font-size\s*:\s*(\d+(?:\.\d+)?|\.\d+)\s*(px|pt|em|rem|%)?", re.IGNORECASE
)
_HEADING_CLASS_RE = re.compile(r"\b(?:h[1-6]|title|chapter-?title|heading|head)\b", re.IGNORECASE)
_FILE_STEM_RE = re.compile(
    r"(?:xhtml|html|ch|chap|chapter|part|sec|section|split|content|text|file|item|page|id)"
    r"[-_.]?\d+(?:[-_.]\d+)*",
    re.IGNORECASE,
)
_EM_PX = 16.0
_CSS_PX_PER_INCH = 96.0
_CSS_PT_PER_INCH = 72.0
_PT_PX = _CSS_PX_PER_INCH / _CSS_PT_PER_INCH
_PERCENT = 100.0
_NO_SIZE_PX = float(0)
_MAX_HEADING_TEXT = 120
_H1_MIN_PX = 28
_H2_MIN_PX = 22
_H3_MIN_PX = 18
_PROMOTABLE_MIN_PX = _H3_MIN_PX


def _font_size_px(style: str) -> float:
    """Return the inline ``font-size`` in pixels, or ``0`` if absent."""
    match = _FONT_SIZE_RE.search(style)
    if not match:
        return _NO_SIZE_PX
    number = float(match.group(1))
    unit = (match.group(2) or "px").lower()
    if unit in {"em", "rem"}:
        return number * _EM_PX
    if unit == "pt":
        return number * _PT_PX
    if unit == "%":
        return number / _PERCENT * _EM_PX
    return number


def _level_for_size(size: float) -> int:
    """Map a pixel font-size to a heading level (pre-shift)."""
    if size >= _H1_MIN_PX:
        return 1
    if size >= _H2_MIN_PX:
        return 2
    if size >= _H3_MIN_PX:
        return 3
    return 4


def _heading_level(meta: ir.Meta, levels: Mapping[str, int]) -> int:
    """Return the heading level a styled paragraph should become, or ``0``."""
    from_stylesheet = next(filter(None, map(levels.get, meta.classes)), 0)
    if from_stylesheet:
        return from_stylesheet
    size = _font_size_px(meta.style)
    if size >= _PROMOTABLE_MIN_PX:
        return _level_for_size(size)
    if any(_HEADING_CLASS_RE.search(name) for name in meta.classes):
        return 2
    return 0


def _promote(block: ir.Block, levels: Mapping[str, int]) -> ir.Block:
    """Promote a styled paragraph to a heading when it looks like one."""
    if not isinstance(block, ir.Paragraph):
        return block
    text = text_of_inlines(block.children).strip()
    if not text or len(text) > _MAX_HEADING_TEXT:
        return block
    level = _heading_level(block.meta, levels)
    if level == 0:
        return block
    return ir.Heading(level=level, children=block.children, meta=block.meta)


def _retitle(chapter: ir.ChapterIR, blocks: tuple[ir.Block, ...]) -> str:
    """Return the chapter title, taking a file-stem-like one from a promoted first heading."""
    first = blocks[0] if blocks else None
    if not isinstance(first, ir.Heading) or first is chapter.blocks[0]:
        return chapter.title
    if not _FILE_STEM_RE.fullmatch(chapter.title):
        return chapter.title
    return text_of_inlines(first.children).strip() or chapter.title


def _log_promotions(before: tuple[ir.Block, ...], after: ir.ChapterIR, audit: AuditLog) -> None:
    """Record each block of *after* that became a heading relative to *before*."""
    for old, new in zip(before, after.blocks, strict=True):
        if isinstance(new, ir.Heading) and new is not old:
            text = text_of_inlines(new.children).strip()
            was, classes = new.meta.tag, new.meta.classes
            audit.add(PromotionRecord(after.title, text, was, classes, new.level))


class FixHeadings(MarkdownExtension):
    """Promote styled paragraphs that act as headings to real headings."""

    name: ClassVar[str] = "fix-headings"

    def transform_chapter(self, chapter: ir.ChapterIR, ctx: ExtCtx) -> ir.ChapterIR:
        """Return *chapter* with styled heading-like paragraphs promoted."""
        levels = classify(ctx.stylesheet) if ctx.stylesheet else {}
        blocks = tuple(_promote(block, levels) for block in chapter.blocks)
        promoted = ir.ChapterIR(
            title=_retitle(chapter, blocks), blocks=blocks, footnotes=chapter.footnotes
        )
        _log_promotions(chapter.blocks, promoted, ctx.audit)
        return promoted
