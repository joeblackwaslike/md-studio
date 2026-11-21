"""Discover available extensions and source fixes (built-ins + entry-points).

Both kinds share one name registry. Built-in names are reserved and the first
registration of any name wins: a third-party entry-point that reuses a taken name is
ignored (with a warning), so installed packages cannot silently shadow shipped or
earlier behaviour. Third-party extensions execute arbitrary code on load — only
install trusted packages.
"""

import logging
from importlib.metadata import EntryPoint, entry_points
from typing import cast

from md_studio.core.extensions.base import MarkdownExtension
from md_studio.core.extensions.fix_broken_links import FixBrokenLinks
from md_studio.core.extensions.fix_headings import FixHeadings
from md_studio.core.extensions.reformat_toc import ReformatToc
from md_studio.core.extensions.remove_footnotes import RemoveFootnotes
from md_studio.core.extensions.source_fix import SourceFix

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "md_studio.extensions"

Registered = type[MarkdownExtension] | type[SourceFix]
Registry = dict[str, Registered]
Failures = dict[str, str]

BUILTINS: tuple[Registered, ...] = (
    FixHeadings,
    RemoveFootnotes,
    FixBrokenLinks,
    ReformatToc,
)


def _builtin_registry() -> Registry:
    """Return the built-in registry keyed by name."""
    return {registered.name: registered for registered in BUILTINS}


def _problem(candidate: object) -> str | None:
    """Return why *candidate* cannot be registered, or ``None`` when it is usable."""
    if not isinstance(candidate, type):
        return "TypeError: not a class"
    name = getattr(candidate, "name", None)
    if not isinstance(name, str) or not name:
        return "TypeError: needs a non-empty string `name`"
    is_extension = issubclass(candidate, MarkdownExtension)
    has_apply = callable(getattr(candidate, "apply", None))
    if is_extension and has_apply:
        return "TypeError: is both a MarkdownExtension and a SourceFix (it defines `apply`)"
    if not is_extension and not has_apply:
        return (
            "TypeError: neither a MarkdownExtension subclass nor a SourceFix (no callable `apply`)"
        )
    return None


def _load(entry: EntryPoint) -> Registered:
    """Load *entry* and return it, raising ``TypeError`` when it is not a usable class."""
    loaded = entry.load()
    problem = _problem(loaded)
    if problem is not None:
        raise TypeError(problem.removeprefix("TypeError: "))
    return cast(Registered, loaded)


def discover_with_failures() -> tuple[Registry, Failures]:
    """Return the available registrations and why some names are unusable.

    The first registration of a name wins (built-ins first). A later entry-point that
    reuses a taken name is dropped and recorded in the failures under that name, so
    asking for the name explicitly can report the collision; so are entry-points that
    fail to load or register something unusable.
    """
    registry = _builtin_registry()
    failures: Failures = {}
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        taken = registry.get(entry.name)
        if taken is not None:
            logger.warning("Ignoring entry-point %r: name already registered", entry.name)
            failures[entry.name] = (
                f"name already registered by {taken.__name__}; entry-point ignored"
            )
            continue
        try:
            registry[entry.name] = _load(entry)
        except Exception as error:
            logger.debug("Failed to load extension %r", entry.name, exc_info=True)
            failures[entry.name] = f"{type(error).__name__}: {error}"
    return registry, failures


def discover() -> Registry:
    """Return all available extensions and source fixes, merging built-ins and entry-points."""
    return discover_with_failures()[0]
