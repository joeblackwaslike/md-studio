"""Collect an EPUB's CSS so extensions can classify styled headings."""

import zipfile
from contextlib import suppress

from lxml import etree

from md_studio.core.exceptions import ReadError
from md_studio.readers.epub import manifest
from md_studio.readers.epub.archive import read_member_prefix
from md_studio.readers.epub.models import CSS_MEDIA_TYPE, MAX_STYLESHEET_BYTES
from md_studio.readers.epub.xml import anywhere, local


def _css_paths(opf_root: etree._Element, opf_dir: str) -> list[str]:  # type: ignore[no-any-unimported]
    """Return archive paths of ``text/css`` manifest items, in manifest order."""
    entries = opf_root.xpath(f"{anywhere('manifest')}/{local('item')}")
    return [
        manifest.resolve(opf_dir, entry.get("href"))
        for entry in entries
        if entry.get("media-type") == CSS_MEDIA_TYPE and entry.get("href")
    ]


def read_stylesheet(  # type: ignore[no-any-unimported]
    archive: zipfile.ZipFile,
    opf_root: etree._Element,
    opf_dir: str,
) -> str:
    """Concatenate the manifest's CSS members with newlines, within a 1 MiB total budget.

    CSS only feeds optional extensions, so a missing, encrypted, corrupt or oversize
    member is skipped (an oversize one is cut at the remaining budget) and never fails
    the book. Reading stops once the budget is spent.

    Parameters
    ----------
    archive:
        An opened EPUB archive.
    opf_root:
        The parsed OPF package document.
    opf_dir:
        Directory of the OPF inside the archive.

    Returns
    -------
    str
        The joined stylesheet text (at most 1 MiB of source bytes), or ``""``.
    """
    sheets: list[str] = []
    remaining = MAX_STYLESHEET_BYTES
    for css_path in _css_paths(opf_root, opf_dir):
        if remaining <= 0:
            break
        with suppress(KeyError, ReadError, zipfile.BadZipFile):
            payload = read_member_prefix(archive, css_path, remaining)
            sheets.append(payload.decode("utf-8", errors="replace"))
            remaining -= len(payload) + 1
    return "\n".join(sheets)
