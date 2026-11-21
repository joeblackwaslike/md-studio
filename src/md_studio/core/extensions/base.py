"""Base class and context for Markdown transformation extensions.

Extensions run on the IR before rendering, so the renderer records line/byte
offsets from their output; extensions never need to adjust offsets themselves. Subclass
:class:`MarkdownExtension` and override only the hooks you need; both default to
identity.
"""

from dataclasses import dataclass, field
from typing import ClassVar

from md_studio.core import ir
from md_studio.core.extensions.audit import AuditLog


@dataclass(frozen=True, slots=True)
class ExtCtx:
    """Context passed to every extension hook.

    The fields are fixed, but ``audit`` is a collector extensions append promotions to.
    """

    book: ir.BookMeta
    anchors: frozenset[str] = field(default_factory=frozenset)
    stylesheet: str = ""
    audit: AuditLog = field(default_factory=AuditLog)


class MarkdownExtension:
    """Base class for IR-stage Markdown extensions."""

    name: ClassVar[str] = ""

    def transform_chapter(self, chapter: ir.ChapterIR, ctx: ExtCtx) -> ir.ChapterIR:
        """Transform a single chapter. Defaults to identity."""
        return chapter

    def transform_book(
        self,
        chapters: tuple[ir.ChapterIR, ...],
        ctx: ExtCtx,
    ) -> tuple[ir.ChapterIR, ...]:
        """Transform the whole book after per-chapter passes. Defaults to identity."""
        return chapters
