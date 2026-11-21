"""Typer application exposing the ``md-studio`` commands."""

from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import Annotated

import typer

from md_studio.cli.vault import VAULT_ENV, SinkChoice, convert_to_vault, require_vault
from md_studio.core.convert import convert as convert_document
from md_studio.core.document import Document
from md_studio.core.exceptions import MdStudioError
from md_studio.readers.epub import read_epub
from md_studio.sinks.file import FileSink

app = typer.Typer(help="Convert EPUB sources to Markdown.", no_args_is_help=True)

_READERS = MappingProxyType({".epub": read_epub})


def _fail(message: str) -> typer.Exit:
    """Print *message* to stderr and return the exit signal to raise."""
    typer.echo(f"Error: {message}", err=True)
    return typer.Exit(code=1)


def _read(source: Path) -> Document:
    """Read *source* with the reader registered for its suffix."""
    reader = _READERS.get(source.suffix.lower())
    if reader is None:
        supported = ", ".join(sorted(_READERS))
        raise _fail(f"Unsupported source type {source.suffix!r}; supported: {supported}")
    return reader(source)


def _split_names(raw: str | None) -> list[str] | None:
    """Split a comma-separated extension list, or return ``None`` when unset.

    Surrounding spaces and empty entries (for example a trailing comma) are ignored.
    A non-empty value that yields no names is an error.
    """
    if raw is None:
        return None
    names = [name.strip() for name in raw.split(",") if name.strip()]
    if not names:
        raise _fail(f"--ext names no extensions: {raw!r}")
    return names


def _same_file(first: Path, second: Path) -> bool:
    """Return whether two paths resolve to, or are hard links of, the same file."""
    try:
        return first.resolve() == second.resolve() or (
            first.exists() and second.exists() and first.samefile(second)
        )
    except (OSError, RuntimeError) as error:
        raise _fail(f"Cannot compare {second} with the source: {error}") from error


def _guarded(action: Callable[[], Path]) -> Path:
    """Run *action*, mapping expected failures to a CLI exit."""
    try:
        return action()
    except (MdStudioError, OSError) as error:
        raise _fail(str(error)) from error


@app.callback()
def main() -> None:
    """Convert documents to Markdown."""


@app.command()
def convert(  # noqa: WPS211 -- one parameter per CLI option
    source: Annotated[Path, typer.Argument(help="Source file to convert.")],
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Destination .md path (default: next to source)."),
    ] = None,
    ext: Annotated[
        str | None,
        typer.Option("--ext", help="Comma-separated extension names, in pipeline order."),
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing file.")] = False,  # noqa: FBT002
    sink: Annotated[
        SinkChoice, typer.Option("--sink", help="Where to write the Markdown.")
    ] = SinkChoice.LOCAL,
    vault: Annotated[
        Path | None,
        typer.Option("--vault", envvar=VAULT_ENV, help="Obsidian vault directory."),
    ] = None,
) -> None:
    """Convert SOURCE to a Markdown file or an Obsidian note."""
    extensions = _split_names(ext)
    if sink is SinkChoice.VAULT:
        vault_dir = _guarded(lambda: require_vault(vault, output=output, force=force))
        written = _guarded(
            lambda: convert_to_vault(
                _read(source), source=source, vault=vault_dir, extensions=extensions
            )
        )
        typer.echo(f"Wrote {written}")
        return
    dest = output or source.with_suffix(".md")
    if _same_file(source, dest):
        raise _fail(f"Output path is the source file: {source}")
    sink_file = FileSink(dest, force=force)
    written = _guarded(
        lambda: sink_file.write(
            convert_document(_read(source), extensions=extensions), name=source.stem
        )
    )
    typer.echo(f"Wrote {written}")
