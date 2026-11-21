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


def open_vault_sink(vault: str | None, *, output: Path | None, force: bool) -> ObsidianSink:
    """Return a checked Obsidian sink for *vault*, rejecting options it cannot honor.

    Parameters
    ----------
    vault:
        Vault directory from ``--vault`` or the environment; ``~`` is expanded.
    output:
        The ``-o`` value, which the Obsidian sink does not accept.
    force:
        The ``--force`` flag, which the Obsidian sink does not accept.

    Raises
    ------
    SinkError
        When ``-o``/``--force`` was given, no vault is configured or it is blank, or the
        vault cannot take a note. Nothing is created in any of those cases.
    """
    if output is not None or force:
        msg = "--sink obsidian does not accept -o/--output or --force"
        raise SinkError(msg)
    if vault is None:
        msg = f"--sink obsidian needs a vault: pass --vault PATH or set {VAULT_ENV}"
        raise SinkError(msg)
    if not vault.strip():
        msg = "--vault is blank: pass the vault directory"
        raise SinkError(msg)
    sink = ObsidianSink(Path(vault).expanduser(), folder=_FOLDER)
    sink.check()
    return sink


def convert_to_vault(
    document: Document, *, source: Path, sink: ObsidianSink, extensions: list[str] | None
) -> Path:
    """Convert *document* with the vault's properties and write it as a new note.

    Raises
    ------
    MdStudioError
        When conversion or the vault check fails.
    OSError
        When the note cannot be written or already exists.
    """
    extra = sink.properties(document.metadata, source=source.name)
    rendered = convert(document, extensions=extensions, extra=extra)
    return sink.write(rendered, name=source.stem)
