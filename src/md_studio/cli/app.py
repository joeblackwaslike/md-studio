"""Typer application exposing the ``md-studio`` commands."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from md_studio.cli import sources
from md_studio.cli.files import convert_to_file
from md_studio.cli.report import report_conversion
from md_studio.cli.vault import VAULT_ENV, SinkChoice, convert_to_vault, open_vault_sink
from md_studio.core.exceptions import MdStudioError

app = typer.Typer(help="Convert EPUB sources to Markdown.", no_args_is_help=True)


def _fail(message: str) -> typer.Exit:
    """Print *message* to stderr and return the exit signal to raise."""
    typer.echo(f"Error: {message}", err=True)
    return typer.Exit(code=1)


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


def _guarded[Produced](action: Callable[[], Produced]) -> Produced:
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
    source: Annotated[str, typer.Argument(help="Source file, URL or arXiv id to convert.")],
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
        str | None,
        typer.Option("--vault", envvar=VAULT_ENV, help="Obsidian vault directory."),
    ] = None,
    arxiv_id: Annotated[
        str | None,
        typer.Option("--arxiv-id", help="Treat the source as this arXiv paper (id or URL)."),
    ] = None,
) -> None:
    """Convert SOURCE to a Markdown file or an Obsidian note."""
    job = _guarded(lambda: sources.prepare(source, arxiv_id, _split_names(ext)))
    if sink is SinkChoice.VAULT:
        vault_sink = _guarded(lambda: open_vault_sink(vault, output=output, force=force))
        outcome = _guarded(
            lambda: convert_to_vault(
                job.document(), source=job.origin, sink=vault_sink, extensions=job.extensions
            )
        )
        typer.echo(f"Wrote {outcome[0]}")
        report_conversion(outcome[1], job.extensions, to_vault=True)
        return
    dest = output or job.origin.with_suffix(".md")
    if job.plan is None and _same_file(job.origin, dest):
        raise _fail(f"Output path is the source file: {source}")
    done = _guarded(
        lambda: convert_to_file(
            job.document(), source=job.origin, dest=dest, extensions=job.extensions, force=force
        )
    )
    typer.echo(f"Wrote {done[0]}")
    if done[1] is not None:
        typer.echo(f"Wrote heading audit {done[1]}")
    report_conversion(done[2], job.extensions)
