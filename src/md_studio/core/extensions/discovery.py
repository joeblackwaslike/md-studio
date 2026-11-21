"""Discover available Markdown extensions (built-ins + entry-points).

Built-in names are reserved: a third-party entry-point that reuses a built-in
name is ignored (with a warning), so installed packages cannot silently shadow
shipped behaviour. Third-party extensions execute arbitrary code on load — only
install trusted packages.
"""

import logging
from importlib.metadata import entry_points

from md_studio.core.extensions.base import MarkdownExtension
from md_studio.core.extensions.fix_broken_links import FixBrokenLinks
from md_studio.core.extensions.fix_headings import FixHeadings
from md_studio.core.extensions.reformat_toc import ReformatToc
from md_studio.core.extensions.remove_footnotes import RemoveFootnotes

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "md_studio.extensions"

_BUILTINS: tuple[type[MarkdownExtension], ...] = (
    FixHeadings,
    RemoveFootnotes,
    FixBrokenLinks,
    ReformatToc,
)


def _builtin_registry() -> dict[str, type[MarkdownExtension]]:
    """Return the built-in extension registry keyed by name."""
    return {extension_cls.name: extension_cls for extension_cls in _BUILTINS}


def discover() -> dict[str, type[MarkdownExtension]]:
    """Return all available extensions, merging built-ins and entry-points."""
    registry = _builtin_registry()
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        if entry.name in registry:
            logger.warning("Ignoring entry-point %r: reserved built-in name", entry.name)
            continue
        try:
            registry[entry.name] = entry.load()
        except Exception:
            logger.exception("Failed to load markdown extension %r", entry.name)
    return registry
