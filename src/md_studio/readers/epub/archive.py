"""Size-capped member reads shared by every EPUB reader module."""

import lzma
import zipfile
import zlib

from md_studio.core.exceptions import ReadError

MAX_MEMBER_BYTES = 67_108_864
_UNREADABLE = (RuntimeError, NotImplementedError, zlib.error, EOFError, lzma.LZMAError, OSError)


def _declared_size(archive: zipfile.ZipFile, path: str) -> int:
    """Return the uncompressed size the archive claims for member *path*."""
    return archive.getinfo(path).file_size


def read_member(archive: zipfile.ZipFile, path: str) -> bytes:
    """Read archive member *path*, refusing members that decompress past the cap.

    Parameters
    ----------
    archive:
        An opened EPUB archive.
    path:
        Member path inside the archive.

    Returns
    -------
    bytes
        The member's decompressed content.

    Raises
    ------
    KeyError
        When the member is absent.
    ReadError
        When the member's declared size exceeds ``MAX_MEMBER_BYTES``, or it is
        encrypted, uses an unsupported compression method, is truncated or corrupt, or
        actually decompresses past the cap despite a smaller declared size.
    """
    size = _declared_size(archive, path)
    if size > MAX_MEMBER_BYTES:
        raise ReadError(f"Archive member {path} exceeds {MAX_MEMBER_BYTES} bytes ({size})")
    try:
        with archive.open(path) as stream:
            payload = stream.read(MAX_MEMBER_BYTES + 1)
    except _UNREADABLE as error:
        raise ReadError(f"Cannot read archive member {path}: {error}") from error
    if len(payload) > MAX_MEMBER_BYTES:
        raise ReadError(f"Archive member {path} exceeds {MAX_MEMBER_BYTES} bytes")
    return payload


def read_member_prefix(archive: zipfile.ZipFile, path: str, limit: int) -> bytes:
    """Read at most *limit* decompressed bytes of member *path*, never more.

    Unlike :func:`read_member` an oversize member is not an error: only the first
    *limit* bytes are decompressed.

    Raises
    ------
    KeyError
        When the member is absent.
    ReadError
        When the member is encrypted, uses an unsupported compression method, or is
        truncated or corrupt.
    """
    try:
        with archive.open(path) as stream:
            return stream.read(limit)
    except _UNREADABLE as error:
        raise ReadError(f"Cannot read archive member {path}: {error}") from error
