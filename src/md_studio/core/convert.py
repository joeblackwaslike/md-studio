"""Top-level Document -> Markdown conversion entry point.

Pipeline: assemble IR -> run extension pipeline -> render body + record
offsets -> build two-pass front matter. Performs no file I/O.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from md_studio.core import assemble, frontmatter, ir
from md_studio.core.document import Document
from md_studio.core.extensions import ExtCtx, pipeline
from md_studio.core.extensions.audit import PromotionRecord
from md_studio.core.render import Renderer


@dataclass(frozen=True, slots=True)
class RenderedMarkdown:
    """The converted Markdown: full text, its front-matter and body parts, and promotions."""

    text: str
    front_matter: str
    body: str
    chapters: tuple[frontmatter.ChapterRange, ...]
    promotions: tuple[PromotionRecord, ...] = ()


def convert(
    document: Document,
    *,
    extensions: list[str] | None = None,
    extra: Mapping[str, str | list[str]] | None = None,
) -> RenderedMarkdown:
    """Convert *document* to Markdown.

    Parameters
    ----------
    document:
        The parsed source document.
    extensions:
        Ordered extension names to run (pipeline order). Defaults to none.
    extra:
        Additional front-matter properties; key rules are documented on
        :func:`md_studio.core.frontmatter.build`.

    Returns
    -------
    RenderedMarkdown
        Full text, front matter, body, and per-chapter byte/line ranges.

    Raises
    ------
    UnknownExtensionError
        When a configured extension name is not registered.
    ExtensionLoadError
        When a requested entry-point extension fails to import.
    MdStudioError
        When an *extra* key is invalid or collides with a reserved key.
    OffsetOverflowError
        When a chapter offset exceeds the fixed front-matter field width.

    """
    meta, chapters = assemble.assemble(document)
    chapters, promotions = _apply_extensions(meta, chapters, extensions or [], document.stylesheet)
    return _render(meta, chapters, extra, promotions)


def _render(
    meta: ir.BookMeta,
    chapters: tuple[ir.ChapterIR, ...],
    extra: Mapping[str, str | list[str]] | None,
    promotions: tuple[PromotionRecord, ...],
) -> RenderedMarkdown:
    """Render *chapters* and build the two-pass front matter around the body."""
    rendered = Renderer().render(chapters)
    front_matter, ranges = frontmatter.build(
        meta,
        [chapter.title for chapter in chapters],
        rendered.offsets,
        rendered.body,
        extra=extra,
    )
    return RenderedMarkdown(
        text=f"{front_matter}{rendered.body}",
        front_matter=front_matter,
        body=rendered.body,
        chapters=tuple(ranges),
        promotions=promotions,
    )


def _apply_extensions(
    meta: ir.BookMeta,
    chapters: tuple[ir.ChapterIR, ...],
    extensions: list[str],
    stylesheet: str,
) -> tuple[tuple[ir.ChapterIR, ...], tuple[PromotionRecord, ...]]:
    """Resolve and run the extension pipeline over *chapters*, returning its promotions too."""
    resolved = pipeline.resolve(extensions)
    anchors = frozenset(note.identifier for chapter in chapters for note in chapter.footnotes)
    ctx = ExtCtx(book=meta, anchors=anchors, stylesheet=stylesheet)
    chapters = pipeline.run(chapters, ctx, resolved)
    return chapters, tuple(ctx.audit.records)
