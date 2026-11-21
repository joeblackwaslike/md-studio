"""Collect an EPUB's CSS so extensions can classify styled headings."""

import zipfile
from contextlib import suppress

from lxml import etree

from md_studio.readers.epub import manifest
from md_studio.readers.epub.archive import read_member
from md_studio.readers.epub.models import CSS_MEDIA_TYPE
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
    """Concatenate the manifest's CSS members with newlines, skipping any the archive lacks.

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
        The joined stylesheet text, or ``""`` when the manifest lists no CSS.

    Raises
    ------
    ReadError
        When a CSS member is oversize, encrypted, or corrupt.
    """
    sheets: list[str] = []
    for css_path in _css_paths(opf_root, opf_dir):
        with suppress(KeyError):
            sheets.append(read_member(archive, css_path).decode("utf-8", errors="replace"))
    return "\n".join(sheets)
