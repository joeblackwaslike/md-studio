"""Typer application exposing the ``md-studio`` commands."""

from pathlib import Path
from types import MappingProxyType
from typing import Annotated

import typer

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
    if not raw:
        return None
    names = [name.strip() for name in raw.split(",") if name.strip()]
    if not names:
        raise _fail(f"--ext names no extensions: {raw!r}")
    return names


def _same_file(first: Path, second: Path) -> bool:
    """Return whether two paths refer to the same file, existing or not."""
    if first.resolve() == second.resolve():
        return True
    return first.exists() and second.exists() and first.samefile(second)


def _convert_to_file(
    source: Path, dest: Path, extensions: list[str] | None, *, force: bool
) -> Path:
    """Read, convert and write *source*, mapping expected failures to a CLI exit."""
    sink = FileSink(dest, force=force)
    try:
        return sink.write(convert_document(_read(source), extensions=extensions), name=source.stem)
    except (MdStudioError, OSError) as error:
        raise _fail(str(error)) from error


@app.callback()
def main() -> None:
    """Convert documents to Markdown."""


@app.command()
def convert(
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
) -> None:
    """Convert SOURCE to a Markdown file."""
    dest = output or source.with_suffix(".md")
    extensions = _split_names(ext)
    if _same_file(source, dest):
        raise _fail(f"Output path is the source file: {source}")
    written = _convert_to_file(source, dest, extensions, force=force)
    typer.echo(f"Wrote {written}")
