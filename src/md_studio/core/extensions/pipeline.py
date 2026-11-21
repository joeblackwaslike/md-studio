"""Resolve and run the configured source fixes and Markdown extensions."""

from md_studio.core import ir
from md_studio.core.document import Document
from md_studio.core.exceptions import ExtensionLoadError, UnknownExtensionError
from md_studio.core.extensions.base import ExtCtx, MarkdownExtension
from md_studio.core.extensions.discovery import Registered, discover_with_failures
from md_studio.core.extensions.source_fix import SourceFix

Resolved = MarkdownExtension | SourceFix


def _instantiate(name: str, registered: Registered) -> Resolved:
    """Construct *registered*, reporting a failed lazy import or an unusable object."""
    try:
        instance = registered()
    except ImportError as error:
        raise ExtensionLoadError(name, f"{type(error).__name__}: {error}") from error
    if not isinstance(instance, MarkdownExtension) and not callable(
        getattr(instance, "apply", None)
    ):
        raise ExtensionLoadError(name, "neither a MarkdownExtension nor a SourceFix (no apply)")
    return instance


def resolve(names: list[str]) -> list[Resolved]:
    """Instantiate the named extensions and source fixes in order.

    Raises
    ------
    UnknownExtensionError
        When a name is not registered.
    ExtensionLoadError
        When an entry-point failed to import or registered an unusable object.
    """
    registry, failures = discover_with_failures()
    resolved: list[Resolved] = []
    for name in names:
        extension_cls = registry.get(name)
        if extension_cls is None and name in failures:
            raise ExtensionLoadError(name, failures[name])
        if extension_cls is None:
            raise UnknownExtensionError(name, sorted(registry))
        resolved.append(_instantiate(name, extension_cls))
    return resolved


def split(resolved: list[Resolved]) -> tuple[list[SourceFix], list[MarkdownExtension]]:
    """Separate resolved names into source fixes and Markdown extensions, keeping order."""
    fixes = [entry for entry in resolved if not isinstance(entry, MarkdownExtension)]
    extensions = [entry for entry in resolved if isinstance(entry, MarkdownExtension)]
    return fixes, extensions


def apply_source_fixes(document: Document, fixes: list[SourceFix]) -> Document:
    """Apply each source fix to *document*, in order."""
    for fix in fixes:
        document = fix.apply(document)
    return document


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
