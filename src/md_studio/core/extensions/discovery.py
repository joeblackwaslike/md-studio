"""Discover available extensions and source fixes (built-ins + entry-points).

Both kinds share one name registry. Built-in names are reserved and the first
registration of any name wins: a third-party entry-point that reuses a taken name is
ignored (with a warning), so installed packages cannot silently shadow shipped or
earlier behaviour. Third-party extensions execute arbitrary code on load — only
install trusted packages.
"""

import logging
from importlib.metadata import entry_points

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


def discover_with_failures() -> tuple[Registry, Failures]:
    """Return the available extensions and the load error text of each failed entry-point."""
    registry = _builtin_registry()
    failures: Failures = {}
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        if entry.name in registry:
            logger.warning("Ignoring entry-point %r: name already registered", entry.name)
            continue
        try:
            registry[entry.name] = entry.load()
        except Exception as error:
            logger.debug("Failed to load markdown extension %r", entry.name, exc_info=True)
            failures[entry.name] = f"{type(error).__name__}: {error}"
    return registry, failures


def discover() -> Registry:
    """Return all available extensions and source fixes, merging built-ins and entry-points."""
    return discover_with_failures()[0]
