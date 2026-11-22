"""Top-level Document -> Markdown conversion entry point.

Pipeline: assemble IR -> run extension pipeline -> render body + record
offsets -> build two-pass front matter. Performs no file I/O.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from md_studio.core import assemble, frontmatter, ir
from md_studio.core.document import Document
from md_studio.core.extensions import ExtCtx, MarkdownExtension, pipeline
from md_studio.core.extensions.audit import PromotionRecord
from md_studio.core.render import Renderer


@dataclass(frozen=True, slots=True)
class RenderedMarkdown:
    """The converted Markdown: full text, front-matter and body parts, promotions and notes.

    ``notes`` describe input an enabled stylesheet-reading extension could not use; they
    are empty for a default conversion.
    """

    text: str
    front_matter: str
    body: str
    chapters: tuple[frontmatter.ChapterRange, ...]
    promotions: tuple[PromotionRecord, ...] = ()
    notes: tuple[str, ...] = ()


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
        Ordered extension and source-fix names to enable. Source fixes run first, in
        listed order, then the Markdown extensions in listed order. Defaults to none.
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
    document, markdown_extensions = _fix_source(document, extensions or [])
    meta, chapters = assemble.assemble(document)
    chapters, ctx = _apply_extensions(meta, chapters, markdown_extensions, document.stylesheet)
    return _render(
        meta,
        chapters,
        extra,
        tuple(ctx.audit),
        _notes(document, markdown_extensions, ctx),
        has_math=document.has_math,
    )


def _notes(document: Document, extensions: list[MarkdownExtension], ctx: ExtCtx) -> tuple[str, ...]:
    """Return reader and extension notes, but only when a stylesheet-reading extension ran."""
    if not any(extension.uses_stylesheet for extension in extensions):
        return ()
    return (*document.warnings, *ctx.notes)


def _render(  # noqa: WPS211 -- one render step; each argument is a distinct pipeline output
    meta: ir.BookMeta,
    chapters: tuple[ir.ChapterIR, ...],
    extra: Mapping[str, str | list[str]] | None,
    promotions: tuple[PromotionRecord, ...],
    notes: tuple[str, ...],
    *,
    has_math: bool,
) -> RenderedMarkdown:
    """Render *chapters* and build the two-pass front matter around the body."""
    rendered = Renderer(has_math=has_math).render(chapters)
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
        notes=notes,
    )


def _fix_source(document: Document, names: list[str]) -> tuple[Document, list[MarkdownExtension]]:
    """Resolve *names*, run the source fixes on *document*, and return the IR extensions."""
    fixes, extensions = pipeline.split(pipeline.resolve(names))
    return pipeline.apply_source_fixes(document, fixes), extensions


def _apply_extensions(
    meta: ir.BookMeta,
    chapters: tuple[ir.ChapterIR, ...],
    extensions: list[MarkdownExtension],
    stylesheet: str,
) -> tuple[tuple[ir.ChapterIR, ...], ExtCtx]:
    """Run the Markdown extensions over *chapters*, returning them with the shared context."""
    anchors = frozenset(note.identifier for chapter in chapters for note in chapter.footnotes)
    ctx = ExtCtx(book=meta, anchors=anchors, stylesheet=stylesheet)
    return pipeline.run(chapters, ctx, extensions), ctx
