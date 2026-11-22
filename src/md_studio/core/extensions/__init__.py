"""Markdown transformation extensions (built-ins + entry-point discovery)."""
# flake8: noqa: WPS412

from md_studio.core.extensions.base import ExtCtx, MarkdownExtension
from md_studio.core.extensions.discovery import ENTRY_POINT_GROUP, discover
from md_studio.core.extensions.fix_broken_links import FixBrokenLinks
from md_studio.core.extensions.fix_headings import FixHeadings
from md_studio.core.extensions.pipeline import resolve, run
from md_studio.core.extensions.reformat_toc import ReformatToc
from md_studio.core.extensions.remove_footnotes import RemoveFootnotes
from md_studio.core.extensions.source_fix import SourceFix

__all__ = [
    "ENTRY_POINT_GROUP",
    "ExtCtx",
    "FixBrokenLinks",
    "FixHeadings",
    "MarkdownExtension",
    "ReformatToc",
    "RemoveFootnotes",
    "SourceFix",
    "discover",
    "resolve",
    "run",
]
