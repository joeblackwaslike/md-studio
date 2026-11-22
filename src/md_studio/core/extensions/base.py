"""Base class and context for Markdown transformation extensions.

Extensions run on the IR before rendering, so the renderer records line/byte
offsets from their output; extensions never need to adjust offsets themselves. Subclass
:class:`MarkdownExtension` and override only the hooks you need; both default to
identity.
"""

from dataclasses import dataclass, field
from typing import ClassVar

from md_studio.core import ir
from md_studio.core.extensions.audit import PromotionRecord


@dataclass(frozen=True, slots=True)
class ExtCtx:
    """Context passed to every extension hook.

    ``audit`` and ``notes`` are collectors extensions append to (promotions, and
    descriptions of input they could not use); they take no part in equality or hashing.
    """

    book: ir.BookMeta
    anchors: frozenset[str] = field(default_factory=frozenset)
    stylesheet: str = ""
    audit: list[PromotionRecord] = field(default_factory=list, compare=False, hash=False)
    notes: list[str] = field(default_factory=list, compare=False, hash=False)


class MarkdownExtension:
    """Base class for IR-stage Markdown extensions."""

    name: ClassVar[str] = ""
    uses_stylesheet: ClassVar[bool] = False

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


def is_extension(candidate: object) -> bool:
    """Return whether *candidate* (a class or an instance) is a :class:`MarkdownExtension`.

    This is the single test that tells the two registry kinds apart: anything that is not
    a Markdown extension must be a source fix (an object with ``apply``).
    """
    if isinstance(candidate, type):
        return issubclass(candidate, MarkdownExtension)
    return isinstance(candidate, MarkdownExtension)
