"""Console reporting for the ``convert`` command: warnings and the promotion count."""

import typer

from md_studio.core.convert import RenderedMarkdown

_FIX_HEADINGS = "fix-headings"
_VAULT_NOTE = " (the audit report is not written for --sink obsidian)"


def report_conversion(
    rendered: RenderedMarkdown, extensions: list[str] | None, *, to_vault: bool = False
) -> None:
    """Print each note as a ``warning:`` line on stderr, then the promotion count.

    Notes only exist when an extension that reads the stylesheet ran and lost something,
    so a default conversion prints none. When ``fix-headings`` ran the count is always
    reported, including zero.
    """
    for note in rendered.notes:
        typer.echo(f"warning: {note}", err=True)
    if _FIX_HEADINGS in (extensions or ()):
        count = len(rendered.promotions)
        suffix = _VAULT_NOTE if to_vault and count else ""
        typer.echo(f"Promoted {count} headings{suffix}")
