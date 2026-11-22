"""Resolve and run the configured source fixes and Markdown extensions."""

from typing import cast

from md_studio.core import ir
from md_studio.core.document import Document
from md_studio.core.exceptions import ExtensionLoadError, UnknownExtensionError
from md_studio.core.extensions.base import ExtCtx, MarkdownExtension, is_extension
from md_studio.core.extensions.discovery import (
    Failures,
    Registered,
    Registry,
    discover_with_failures,
)
from md_studio.core.extensions.source_fix import SourceFix

Resolved = MarkdownExtension | SourceFix


def _instantiate(name: str, registered: Registered) -> Resolved:
    """Construct *registered*, reporting any constructor failure as a load error."""
    try:
        return registered()
    except Exception as error:
        raise ExtensionLoadError(name, f"{type(error).__name__}: {error}") from error


def _lookup(name: str, registry: Registry, failures: Failures) -> Registered:
    """Return the retained registration for *name*, raising when there is none."""
    registered = registry.get(name)
    if registered is not None:
        return registered
    failure = failures.get(name)
    if failure is not None:
        raise ExtensionLoadError(name, failure)
    raise UnknownExtensionError(name, sorted(registry))


def resolve(names: list[str]) -> list[Resolved]:
    """Instantiate the named extensions and source fixes in order.

    Raises
    ------
    UnknownExtensionError
        When a name is not registered.
    ExtensionLoadError
        When the name has no usable registration because its entry-point failed to load or
        registered an unusable object, or when its constructor raised.
    """
    registry, failures = discover_with_failures()
    return [_instantiate(name, _lookup(name, registry, failures)) for name in names]


def split(resolved: list[Resolved]) -> tuple[list[SourceFix], list[MarkdownExtension]]:
    """Separate resolved names into source fixes and Markdown extensions, keeping order."""
    fixes: list[SourceFix] = []
    extensions: list[MarkdownExtension] = []
    for entry in resolved:
        if is_extension(entry):
            extensions.append(cast(MarkdownExtension, entry))
        else:
            fixes.append(cast(SourceFix, entry))
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
