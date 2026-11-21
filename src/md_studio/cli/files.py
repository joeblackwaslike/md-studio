"""File-sink conversion used by the ``convert`` command."""

from pathlib import Path

from md_studio.core.convert import RenderedMarkdown, convert
from md_studio.core.document import Document
from md_studio.core.extensions import audit
from md_studio.sinks.file import FileSink


def _write_audit(rendered: RenderedMarkdown, dest: Path, *, force: bool) -> Path | None:
    """Write the promotion report next to *dest*, or return ``None`` when nothing was promoted."""
    if not rendered.promotions:
        return None
    audit_path = dest.with_name(f"{dest.stem}.audit.md")
    with audit_path.open("w" if force else "x", encoding="utf-8") as stream:
        stream.write(audit.render(rendered.promotions))
    return audit_path


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
    """
    rendered = convert(document, extensions=extensions)
    written = FileSink(dest, force=force).write(rendered, name=source.stem)
    return written, _write_audit(rendered, dest, force=force)
