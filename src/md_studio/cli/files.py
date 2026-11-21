"""File-sink conversion used by the ``convert`` command."""

from pathlib import Path

from md_studio.core.convert import RenderedMarkdown, convert
from md_studio.core.document import Document
from md_studio.core.extensions import audit
from md_studio.sinks.file import FileSink


def _audit_target(rendered: RenderedMarkdown, dest: Path, *, force: bool) -> Path | None:
    """Return where the promotion report goes, or ``None`` when nothing was promoted.

    Applies the file sink's destination checks, so a refused report is known before
    anything is written.
    """
    if not rendered.promotions:
        return None
    target = dest.with_name(f"{dest.stem}.audit.md")
    if target.is_symlink():
        msg = f"Destination is a symlink: {target}"
        raise OSError(msg)
    if target.is_dir():
        msg = f"Destination is a directory: {target}"
        raise IsADirectoryError(msg)
    if target.exists() and not force:
        msg = f"Refusing to overwrite existing file: {target}"
        raise FileExistsError(msg)
    return target


def _write_audit(rendered: RenderedMarkdown, target: Path, *, force: bool) -> None:
    """Write the promotion report to *target* (exclusively unless *force*)."""
    with target.open("w" if force else "x", encoding="utf-8") as stream:
        stream.write(audit.render(rendered.promotions))


def convert_to_file(
    document: Document,
    *,
    source: Path,
    dest: Path,
    extensions: list[str] | None,
    force: bool,
) -> tuple[Path, Path | None]:
    """Convert *document* to *dest* and, when headings were promoted, write ``<stem>.audit.md``.

    Returns
    -------
    tuple[Path, Path | None]
        The Markdown path and the audit report path (``None`` when nothing was promoted).

    Raises
    ------
    MdStudioError
        When conversion fails.
    OSError
        When the Markdown or the audit report cannot be written, or exists without *force*.
        The audit target is checked before the Markdown is written.
    """
    rendered = convert(document, extensions=extensions)
    target = _audit_target(rendered, dest, force=force)
    written = FileSink(dest, force=force).write(rendered, name=source.stem)
    if target is not None:
        _write_audit(rendered, target, force=force)
    return written, target
