"""Top-level Document -> Markdown conversion entry point.

Pipeline: assemble IR -> run extension pipeline -> render body + record
offsets -> build two-pass front matter. Performs no file I/O.
"""

from dataclasses import dataclass

from md_studio.core import assemble, frontmatter, ir
from md_studio.core.document import Document
from md_studio.core.extensions import ExtCtx, pipeline
from md_studio.core.render import Renderer


@dataclass(frozen=True, slots=True)
class RenderedMarkdown:
    """The converted Markdown: full text plus its front-matter and body parts."""

    text: str
    front_matter: str
    body: str
    chapters: tuple[frontmatter.ChapterRange, ...]


def convert(document: Document, *, extensions: list[str] | None = None) -> RenderedMarkdown:
    """Convert *document* to Markdown.

    Parameters
    ----------
    document:
        The parsed source document.
    extensions:
        Ordered extension names to run (pipeline order). Defaults to none.

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
    OffsetOverflowError
        When a chapter offset exceeds the fixed front-matter field width.

    """
    meta, chapters = assemble.assemble(document)
    chapters = _apply_extensions(meta, chapters, extensions or [])

    rendered = Renderer().render(chapters)
    front_matter, ranges = frontmatter.build(
        meta,
        [chapter.title for chapter in chapters],
        rendered.offsets,
        rendered.body,
    )
    return RenderedMarkdown(
        text=f"{front_matter}{rendered.body}",
        front_matter=front_matter,
        body=rendered.body,
        chapters=tuple(ranges),
    )


def _apply_extensions(
    meta: ir.BookMeta,
    chapters: tuple[ir.ChapterIR, ...],
    extensions: list[str],
) -> tuple[ir.ChapterIR, ...]:
    """Resolve and run the configured extension pipeline over *chapters*."""
    resolved = pipeline.resolve(extensions)
    anchors = frozenset(note.identifier for chapter in chapters for note in chapter.footnotes)
    ctx = ExtCtx(book=meta, anchors=anchors)
    return pipeline.run(chapters, ctx, resolved)
