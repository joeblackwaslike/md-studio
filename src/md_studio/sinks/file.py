"""Sink that writes Markdown to a single file."""

import os
import shutil
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from md_studio.core.convert import RenderedMarkdown

_CREATE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL
_PRIVATE_MODE = 0o600
_DEFAULT_MODE = 0o666


def _create_exclusive(path: Path, mode: int) -> int:
    """Create *path* (failing if it exists) with *mode* and return its descriptor."""
    return os.open(path, _CREATE_FLAGS, mode)


def _fill(descriptor: int, payload: bytes) -> None:
    """Write *payload* to the open *descriptor* and close it."""
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)


def _write_new(path: Path, payload: bytes, mode: int) -> None:
    """Create *path* exclusively and write *payload*; remove it if the write fails.

    Only a file this call created is removed: a failure to create (for example an
    existing file or an exhausted descriptor table) leaves *path* untouched.
    """
    descriptor = _create_exclusive(path, mode)
    try:
        _fill(descriptor, payload)
    except BaseException:
        with suppress(OSError):
            path.unlink(missing_ok=True)
        raise


def _staging_path(dest: Path) -> Path:
    """Return a unique hidden sibling of *dest*, short enough for any destination name."""
    return dest.with_name(f".md-studio-{uuid4().hex}.tmp")


def _gid(path: Path) -> int:
    """Return the owning group id of *path*."""
    return path.stat().st_gid


def _match_group(staging: Path, dest: Path) -> None:
    """Give *staging* the group of *dest*, refusing when that group cannot be assigned."""
    if _gid(staging) == _gid(dest):
        return
    try:
        os.chown(staging, -1, _gid(dest))
    except PermissionError as error:
        msg = f"Cannot preserve group of {dest}; refusing to replace"
        raise PermissionError(msg) from error


def _stage_and_move(staging: Path, dest: Path, payload: bytes) -> None:
    """Write *payload* privately to *staging*, match *dest*'s mode, move it over *dest*."""
    _write_new(staging, payload, _PRIVATE_MODE)
    _match_group(staging, dest)
    shutil.copymode(dest, staging)
    os.replace(staging, dest)  # noqa: PTH105


class FileSink:
    """Write rendered Markdown to a fixed destination path."""

    def __init__(self, dest: Path, *, force: bool = False) -> None:
        """Configure the destination and whether an existing file may be replaced."""
        self._dest = dest
        self._force = force

    def write(self, rendered: RenderedMarkdown, *, name: str) -> Path:
        """Write ``rendered.text`` as UTF-8 bytes to the destination, creating parent directories.

        Without ``force`` the file is created exclusively. With ``force`` the content is
        written to a sibling temporary file and moved over the destination, so a failure
        leaves any existing file intact.

        Parameters
        ----------
        rendered:
            The converted Markdown.
        name:
            Accepted for the ``Sink`` protocol; unused.

        Returns
        -------
        Path
            The written file path.

        Raises
        ------
        FileExistsError
            When the destination exists and ``force`` is false.
        IsADirectoryError
            When the destination is a directory.
        OSError
            When the destination is a symlink or the file cannot be written.
        """
        if self._dest.is_symlink():
            msg = f"Destination is a symlink: {self._dest}"
            raise OSError(msg)
        if self._dest.is_dir():
            msg = f"Destination is a directory: {self._dest}"
            raise IsADirectoryError(msg)
        self._dest.parent.mkdir(parents=True, exist_ok=True)
        payload = rendered.text.encode("utf-8")
        if self._force:
            self._replace(payload)
        else:
            self._create(payload)
        return self._dest

    def _create(self, payload: bytes) -> None:
        """Write *payload* to a new file, refusing to overwrite an existing one."""
        try:
            _write_new(self._dest, payload, _DEFAULT_MODE)
        except FileExistsError as error:
            msg = f"Refusing to overwrite existing file: {self._dest}"
            raise FileExistsError(msg) from error

    def _replace(self, payload: bytes) -> None:
        """Replace the destination atomically via a private sibling temporary file."""
        if not self._dest.exists():
            self._create(payload)
            return
        staging = _staging_path(self._dest)
        try:
            _stage_and_move(staging, self._dest, payload)
        except BaseException:
            with suppress(OSError):
                staging.unlink(missing_ok=True)
            raise
