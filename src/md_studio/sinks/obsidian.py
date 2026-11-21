"""Sink that writes Markdown as a note inside an Obsidian vault."""

import os
import unicodedata
from datetime import UTC, datetime
from pathlib import Path, PurePath

from md_studio.core.convert import RenderedMarkdown
from md_studio.core.document import DocumentMetadata
from md_studio.sinks import SinkError
from md_studio.sinks.file import FileSink

_UNSAFE_CHARS = '\N{REVERSE SOLIDUS}/:*?"<>|#^[]'
_STRIPPED_CATEGORIES = ("Cc", "Cf", "Cs", "Co")
_MAX_STEM_BYTES = 237
_SUFFIX = ".md"
_FALLBACK_NAME = "untitled"
_NOTE_TYPE = "book-note"
_NOTE_TAGS = ("book-notes",)
_NOTE_STATUS = "draft"


def is_relative_folder(folder: PurePath) -> bool:
    """Return whether *folder* is a non-empty path that stays under the vault.

    Rooted, drive-anchored (``D:Notes``) and ``..``-containing paths are rejected.
    """
    return bool(folder.parts) and not folder.anchor and ".." not in folder.parts


def _is_unsafe(char: str) -> bool:
    """Return whether *char* must not appear in a note filename."""
    return char in _UNSAFE_CHARS or unicodedata.category(char) in _STRIPPED_CATEGORIES


def sanitize_note_name(name: str) -> str:
    """Return *name* reduced to a filename stem Obsidian and common filesystems accept.

    Characters that filesystems reject (slash, backslash, ``: * ? " < > |``), that break Obsidian
    links (``# ^ [ ]``), and every character in the Unicode categories Cc, Cf, Cs
    and Co (controls, DEL, C1, zero-width, bidi and format characters, surrogates,
    private use) become spaces. Whitespace is collapsed, and leading and trailing dots
    and spaces are removed. The stem is cut to fit 237 UTF-8 bytes, so ``<stem>.md``
    stays within the common 240-byte component limit without splitting a character.
    An empty result becomes ``untitled``.
    """
    spaced = "".join(" " if _is_unsafe(char) else char for char in name)
    cleaned = " ".join(spaced.split()).lstrip(". ")
    clipped = cleaned.encode("utf-8")[:_MAX_STEM_BYTES].decode("utf-8", errors="ignore")
    return clipped.rstrip(". ") or _FALLBACK_NAME


class ObsidianSink:
    """Write rendered Markdown as a new note under ``<vault>/<folder>``."""

    def __init__(self, vault: Path, *, folder: str) -> None:
        """Configure the vault root and the folder, relative to it, that holds the notes.

        Raises
        ------
        SinkError
            When *folder* is empty, rooted, drive-anchored, or contains ``..``.
        """
        if not is_relative_folder(PurePath(folder)):
            msg = f"Folder must be a non-empty relative path without '..': {folder!r}"
            raise SinkError(msg)
        self._vault = vault
        self._folder = folder

    def properties(self, metadata: DocumentMetadata, *, source: str) -> dict[str, str | list[str]]:
        """Return the vault properties to pass to ``convert(extra=...)``.

        Title and authors are already written by the front-matter builder, so this adds
        the vault's own properties: ``type``, ``status``, ``tags``, ``created`` (ISO
        date), ``source`` and, when the document has authors, ``author`` (the vault's
        list-valued spelling).

        Parameters
        ----------
        metadata:
            Metadata of the document about to be converted.
        source:
            Where the document came from, such as the source file name.
        """
        extra: dict[str, str | list[str]] = {
            "source": source,
            "type": _NOTE_TYPE,
            "status": _NOTE_STATUS,
            "created": datetime.now(UTC).astimezone().date().isoformat(),
            "tags": list(_NOTE_TAGS),
        }
        if metadata.authors:
            extra["author"] = list(metadata.authors)
        return extra

    def check(self) -> None:
        """Verify the destination can take a note, creating nothing.

        Raises
        ------
        SinkError
            When the vault is missing, not a directory, or not writable, or when the
            notes folder (or a parent of it) exists as something other than a directory or
            the directory where creation starts is not writable.
        """
        if not self._vault.is_dir():
            msg = f"Vault is not a directory: {self._vault}"
            raise SinkError(msg)
        if not os.access(self._vault, os.W_OK | os.X_OK):
            msg = f"Vault is not writable: {self._vault}"
            raise SinkError(msg)
        creation_dir = self._creation_dir()
        writable = os.access(creation_dir, os.W_OK | os.X_OK)
        if not writable:
            msg = f"Notes folder is not writable: {creation_dir}"
            raise SinkError(msg)

    def write(self, rendered: RenderedMarkdown, *, name: str) -> Path:
        """Write *rendered* as ``<vault>/<folder>/<sanitized name>.md``, creating the folder.

        Parameters
        ----------
        rendered:
            The converted Markdown, whose front matter already carries the properties.
        name:
            Note name; unsafe characters are replaced.

        Returns
        -------
        Path
            The written note path.

        Raises
        ------
        SinkError
            When the vault is missing, not a directory, or not writable. Nothing is
            created in that case.
        FileExistsError
            When a note with that name already exists.
        """
        self.check()
        dest = self._vault / self._folder / f"{sanitize_note_name(name)}{_SUFFIX}"
        return FileSink(dest).write(rendered, name=name)

    def _creation_dir(self) -> Path:
        """Return the deepest existing directory on the notes path, where creation starts.

        Raises
        ------
        SinkError
            When an existing component of the notes path is not a directory.
        """
        current = self._vault
        for part in PurePath(self._folder).parts:
            candidate = current / part
            if not candidate.exists():
                break
            if not candidate.is_dir():
                msg = f"Notes folder is not a directory: {candidate}"
                raise SinkError(msg)
            current = candidate
        return current
