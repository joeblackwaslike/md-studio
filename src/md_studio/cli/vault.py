"""Obsidian-specific conversion used by the ``convert`` command."""

from enum import StrEnum
from pathlib import Path

from md_studio.core.convert import convert
from md_studio.core.document import Document
from md_studio.sinks import SinkError
from md_studio.sinks.obsidian import ObsidianSink

VAULT_ENV = "MD_STUDIO_VAULT"
_FOLDER = "Book Notes"


class SinkChoice(StrEnum):
    """Where converted Markdown is written."""

    LOCAL = "file"
    VAULT = "obsidian"


def require_vault(vault: Path | None, *, output: Path | None, force: bool) -> Path:
    """Return the configured *vault*, rejecting options the Obsidian sink cannot honor.

    Raises
    ------
    SinkError
        When ``-o``/``--force`` was given or no vault is configured.
    """
    if output is not None or force:
        msg = "--sink obsidian does not accept -o/--output or --force"
        raise SinkError(msg)
    if vault is None:
        msg = f"--sink obsidian needs a vault: pass --vault PATH or set {VAULT_ENV}"
        raise SinkError(msg)
    return vault


def convert_to_vault(
    document: Document, *, source: Path, vault: Path, extensions: list[str] | None
) -> Path:
    """Convert *document* with the vault's properties and write it as a new note.

    Raises
    ------
    MdStudioError
        When conversion or the vault check fails.
    OSError
        When the note cannot be written or already exists.
    """
    sink = ObsidianSink(vault, folder=_FOLDER)
    extra = sink.properties(document.metadata, source=source.name)
    rendered = convert(document, extensions=extensions, extra=extra)
    return sink.write(rendered, name=source.stem)
