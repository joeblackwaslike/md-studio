"""Collect an EPUB's CSS so extensions can classify styled headings."""

import zipfile
from dataclasses import dataclass, field
from typing import NamedTuple

from lxml import etree

from md_studio.core.document import STYLESHEET_SEPARATOR
from md_studio.core.exceptions import ReadError
from md_studio.readers.epub import manifest
from md_studio.readers.epub.archive import read_member_prefix
from md_studio.readers.epub.models import CSS_MEDIA_TYPE, MAX_CSS_MEMBERS, MAX_STYLESHEET_BYTES
from md_studio.readers.epub.xml import anywhere, local

_NUL = "\x00"
_REPLACEMENT = "�"


class StylesheetRead(NamedTuple):
    """The joined CSS of an EPUB and what could not be read."""

    text: str
    warnings: tuple[str, ...]


def _css_paths(opf_root: etree._Element, opf_dir: str) -> list[str]:  # type: ignore[no-any-unimported]
    """Return archive paths of ``text/css`` manifest items, in manifest order, de-duplicated."""
    entries = opf_root.xpath(f"{anywhere('manifest')}/{local('item')}")
    paths = (
        manifest.resolve(opf_dir, entry.get("href"))
        for entry in entries
        if entry.get("media-type") == CSS_MEDIA_TYPE and entry.get("href")
    )
    return list(dict.fromkeys(paths))


def _decode(payload: bytes, path: str, warnings: list[str]) -> str:
    """Decode a sheet (a BOM is dropped), replacing invalid bytes and NULs, and noting it."""
    text = payload.decode("utf-8-sig", errors="replace")
    if _REPLACEMENT in text or _NUL in text:
        warnings.append(f"CSS member {path} has invalid characters; they were replaced")
    return text.replace(_NUL, _REPLACEMENT)


@dataclass(slots=True)
class _Reader:
    """Reads CSS members one by one against a shared byte budget."""

    archive: zipfile.ZipFile
    remaining: int = MAX_STYLESHEET_BYTES
    attempted: int = 0
    sheets: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def read(self, path: str) -> None:
        """Read member *path*; every attempt, failed or not, spends at least one byte."""
        self.attempted += 1
        payload = self._fetch(path)
        self.remaining -= 1 if payload is None else len(payload) + 1
        if payload is not None:
            self.sheets.append(_decode(payload, path, self.warnings))

    def _fetch(self, path: str) -> bytes | None:
        """Read up to the remaining budget of *path*, or ``None`` when it is unreadable."""
        try:
            payload = read_member_prefix(self.archive, path, self.remaining + 1)
        except (KeyError, ReadError, zipfile.BadZipFile) as error:
            reason = "missing" if isinstance(error, KeyError) else str(error)
            self.warnings.append(f"CSS member {path} was skipped: {reason}")
            return None
        if len(payload) > self.remaining:
            self.warnings.append(f"CSS member {path} was cut: the 1 MiB CSS budget ran out")
        return payload[: self.remaining]


def read_stylesheet(  # type: ignore[no-any-unimported]
    archive: zipfile.ZipFile,
    opf_root: etree._Element,
    opf_dir: str,
) -> StylesheetRead:
    """Join the manifest's CSS members within a 1 MiB total budget, never failing the book.

    CSS only feeds optional extensions, so a missing, encrypted, corrupt or oversize
    member is skipped (an oversize one is cut at the remaining budget) and noted in the
    warnings. Members are de-duplicated, at most 256 are read, and every attempt, failed
    or not, spends at least one byte of budget. A leading BOM is dropped.

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
    StylesheetRead
        The sheets joined by :data:`md_studio.core.document.STYLESHEET_SEPARATOR`, and
        warnings describing anything skipped, cut or replaced.
    """
    reader = _Reader(archive)
    paths = _css_paths(opf_root, opf_dir)
    for path in paths[:MAX_CSS_MEMBERS]:
        if reader.remaining <= 0:
            break
        reader.read(path)
    skipped = min(len(paths), MAX_CSS_MEMBERS) - reader.attempted
    if skipped:
        reader.warnings.append(f"{skipped} CSS member(s) were not read: the CSS budget ran out")
    if len(paths) > MAX_CSS_MEMBERS:
        reader.warnings.append(f"only the first {MAX_CSS_MEMBERS} CSS members were read")
    return StylesheetRead(STYLESHEET_SEPARATOR.join(reader.sheets), tuple(reader.warnings))
