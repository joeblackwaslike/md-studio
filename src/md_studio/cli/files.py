"""File-sink conversion used by the ``convert`` command."""

from pathlib import Path

from md_studio.core.convert import RenderedMarkdown, convert
from md_studio.core.document import Document
from md_studio.core.extensions import audit
from md_studio.sinks.file import FileSink


def _audit_sink(rendered: RenderedMarkdown, dest: Path, *, force: bool) -> FileSink | None:
    """Return the sink for the promotion report next to *dest*, or ``None`` if nothing moved.

    The sink's checks run here, so a refused report is known before the Markdown is written.

    Raises
    ------
    OSError
        When *dest* has no file name to derive the report name from, or the report path
        is a symlink, a directory, or exists without *force*.
    """
    if not rendered.promotions:
        return None
    try:
        target = dest.with_name(f"{dest.stem}.audit.md")
    except ValueError as error:
        msg = f"Cannot place the audit report next to {dest}: {error}"
        raise OSError(msg) from error
    sink = FileSink(target, force=force)
    sink.check()
    return sink


def convert_to_file(
    document: Document,
    *,
    source: Path,
    dest: Path,
    extensions: list[str] | None,
    force: bool,
) -> tuple[Path, Path | None, RenderedMarkdown]:
    """Convert *document* to *dest* and, when headings were promoted, write ``<stem>.audit.md``.

    Returns
    -------
    tuple[Path, Path | None, RenderedMarkdown]
        The Markdown path, the audit report path (``None`` when nothing was promoted) and
        the conversion result.

    Raises
    ------
    MdStudioError
        When conversion fails.
    OSError
        When the Markdown cannot be written, or the audit report cannot be (checked before
        the Markdown is written; a failure after it says which file was written).
    """
    rendered = convert(document, extensions=extensions)
    audit_sink = _audit_sink(rendered, dest, force=force)
    written = FileSink(dest, force=force).write(rendered, name=source.stem)
    if audit_sink is None:
        return written, None, rendered
    try:
        report = audit_sink.write_text(audit.render(rendered.promotions))
    except OSError as error:
        msg = f"wrote {written} but audit failed: {error}"
        raise OSError(msg) from error
    return written, report, rendered
