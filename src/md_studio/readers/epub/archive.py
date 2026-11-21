"""Size-capped member reads shared by every EPUB reader module."""

import zipfile

from md_studio.core.exceptions import ReadError

MAX_MEMBER_BYTES = 67_108_864


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
        When the member's declared size exceeds ``MAX_MEMBER_BYTES``.
    """
    size = archive.getinfo(path).file_size
    if size > MAX_MEMBER_BYTES:
        raise ReadError(f"Archive member {path} exceeds {MAX_MEMBER_BYTES} bytes ({size})")
    return archive.read(path)
