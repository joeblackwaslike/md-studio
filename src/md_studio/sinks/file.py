"""Sink that writes Markdown to a single file."""

import os
import shutil
from pathlib import Path
from uuid import uuid4

from md_studio.core.convert import RenderedMarkdown


def _write_exclusive(path: Path, payload: bytes) -> None:
    """Create *path* (failing if it exists) and write *payload* bytes."""
    with path.open("xb") as stream:
        stream.write(payload)


def _staging_path(dest: Path) -> Path:
    """Return a unique hidden sibling of *dest* to stage a replacement in."""
    return dest.with_name(f".{dest.name}.{uuid4().hex}.tmp")


def _stage_and_move(staging: Path, dest: Path, payload: bytes) -> None:
    """Write *payload* to *staging*, then atomically move it over *dest*."""
    _write_exclusive(staging, payload)
    if dest.exists():
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
            _write_exclusive(self._dest, payload)
        except FileExistsError as error:
            msg = f"Refusing to overwrite existing file: {self._dest}"
            raise FileExistsError(msg) from error
        except OSError:
            self._dest.unlink(missing_ok=True)
            raise

    def _replace(self, payload: bytes) -> None:
        """Write *payload* to a sibling temporary file and move it over the destination."""
        staging = _staging_path(self._dest)
        try:
            _stage_and_move(staging, self._dest, payload)
        except BaseException:
            staging.unlink(missing_ok=True)
            raise
