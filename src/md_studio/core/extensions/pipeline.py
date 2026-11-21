"""Resolve and run the configured Markdown extension pipeline."""

from md_studio.core import ir
from md_studio.core.exceptions import ExtensionLoadError, UnknownExtensionError
from md_studio.core.extensions.base import ExtCtx, MarkdownExtension
from md_studio.core.extensions.discovery import discover_with_failures


def resolve(names: list[str]) -> list[MarkdownExtension]:
    """Instantiate the named extensions in order, raising on unknown or unloadable names."""
    registry, failures = discover_with_failures()
    resolved: list[MarkdownExtension] = []
    for name in names:
        extension_cls = registry.get(name)
        if extension_cls is None and name in failures:
            raise ExtensionLoadError(name, failures[name])
        if extension_cls is None:
            raise UnknownExtensionError(name, sorted(registry))
        resolved.append(extension_cls())
    return resolved


def run(
    chapters: tuple[ir.ChapterIR, ...],
    ctx: ExtCtx,
    extensions: list[MarkdownExtension],
) -> tuple[ir.ChapterIR, ...]:
    """Apply each extension's per-chapter then book-level hooks, in order."""
    for extension in extensions:
        chapters = tuple(extension.transform_chapter(chapter, ctx) for chapter in chapters)
        chapters = tuple(extension.transform_book(chapters, ctx))
    return chapters
