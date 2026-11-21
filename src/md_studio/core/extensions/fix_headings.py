"""Extension: promote font-size/styled paragraphs to real headings.

Some books encode structure with styled paragraphs instead of ``<h1>``-``<h6>``.
This promotes those to real headings so the document gets a usable outline. When
the source supplies a stylesheet, classes it styles as headings (see
:mod:`md_studio.core.extensions.css_headings`) decide the level; otherwise an inline
``font-size`` or a heading-ish class name does. Heading levels here are pre-shift;
the renderer demotes them by one under the chapter ``##`` heading. Every promotion
is logged to ``ctx.audit``.
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


def _stylesheet_level(meta: ir.Meta, levels: Mapping[str, int]) -> int:
    """Return the level the stylesheet gives the first matching class, or ``0``."""
    return next((levels[name] for name in meta.classes if name in levels), 0)


def _heading_level(meta: ir.Meta, levels: Mapping[str, int]) -> int:
    """Return the heading level a styled paragraph should become, or ``0``."""
    from_stylesheet = _stylesheet_level(meta, levels)
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


def _log_promotions(chapter: ir.ChapterIR, after: tuple[ir.Block, ...], audit: AuditLog) -> None:
    """Record each block that became a heading when *chapter*'s blocks turned into *after*."""
    for old, new in zip(chapter.blocks, after, strict=True):
        if isinstance(new, ir.Heading) and new is not old:
            text = text_of_inlines(new.children).strip()
            was, classes = new.meta.tag, new.meta.classes
            audit.add(PromotionRecord(chapter.title, text, was, classes, new.level))


class FixHeadings(MarkdownExtension):
    """Promote styled paragraphs that act as headings to real headings."""

    name: ClassVar[str] = "fix-headings"

    def transform_chapter(self, chapter: ir.ChapterIR, ctx: ExtCtx) -> ir.ChapterIR:
        """Return *chapter* with styled heading-like paragraphs promoted."""
        levels = classify(ctx.stylesheet) if ctx.stylesheet else {}
        blocks = tuple(_promote(block, levels) for block in chapter.blocks)
        _log_promotions(chapter, blocks, ctx.audit)
        return ir.ChapterIR(title=chapter.title, blocks=blocks, footnotes=chapter.footnotes)
