"""Read a built EPUB archive into chapters and metadata for Markdown export.

The reader is deliberately decoupled from the download pipeline: it parses the
``.epub`` zip directly (``META-INF/container.xml`` -> OPF -> manifest + spine ->
chapter XHTML), so it works on any EPUB, including ones downloaded earlier.
"""

import posixpath
import zipfile
from pathlib import Path

from md_studio.core.document import Document
from md_studio.core.exceptions import ReadError
from md_studio.readers.epub import chapters, manifest, metadata
from md_studio.readers.epub.xml import parse_xml


def _read_member(archive: zipfile.ZipFile, path: str) -> bytes:
    """Read an archive member, raising :class:`ReadError` if absent."""
    try:
        return archive.read(path)
    except KeyError as exc:
        raise ReadError(f"OPF not found in archive: {path}") from exc


def _read_document(archive: zipfile.ZipFile, source_name: str) -> Document:
    """Parse an opened EPUB archive into an :class:`Document`."""
    opf_path = manifest.opf_path(archive)
    opf_root = parse_xml(_read_member(archive, opf_path), source=opf_path)
    opf_dir = posixpath.dirname(opf_path)
    return Document(
        metadata=metadata.read_metadata(opf_root, source_file=source_name),
        chapters=chapters.spine_chapters(archive, opf_root, opf_dir),
    )


def read_epub(path: Path) -> Document:
    """Read *path* into an :class:`Document`.

    Parameters
    ----------
    path:
        Path to a ``.epub`` archive.

    Returns
    -------
    Document
        Metadata and chapters (in spine order).

    Raises
    ------
    ReadError
        When the archive is missing, not a zip, or structurally invalid.

    """
    if not path.is_file():
        raise ReadError(f"EPUB not found: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            return _read_document(archive, path.name)
    except zipfile.BadZipFile as exc:
        raise ReadError(f"Not a valid EPUB (zip) file: {path}") from exc
