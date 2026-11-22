"""Read a PDF into a chapter-split Document through a pluggable PDF engine."""

from pathlib import Path
from tempfile import TemporaryDirectory

from lxml import etree
from lxml import html as lxml_html

from md_studio.core.document import Document, DocumentMetadata
from md_studio.core.exceptions import ReadError
from md_studio.readers import limits
from md_studio.readers.pdf_chapters import split_chapters
from md_studio.readers.pdf_engines import DoclingEngine, PdfEngine


def _check_file(path: Path) -> None:
    try:
        size = path.stat().st_size if path.is_file() else None
    except OSError as error:
        raise ReadError(f"Could not read {path}: {error}") from error
    if size is None:
        raise ReadError(f"Could not read {path}: not a file")
    if size > limits.MAX_BYTES:
        raise ReadError(limits.TOO_BIG)


def _to_html(path: Path, engine: PdfEngine) -> str:
    with TemporaryDirectory() as scratch:
        return engine.to_html(path, Path(scratch))


def _parse(path: Path, html: str) -> lxml_html.HtmlElement:  # type: ignore[no-any-unimported]
    try:
        return lxml_html.document_fromstring(html)
    except (etree.ParserError, etree.XMLSyntaxError) as exc:
        raise ReadError(f"Could not parse the converted text of {path.name}: {exc}") from exc


def read_pdf(source: Path | str, *, engine: PdfEngine | None = None) -> Document:
    """Read a local PDF into a :class:`Document` with one chapter per top-level heading.

    Chapters follow the PDF outline when it has one, otherwise the engine's headings, and
    record the first and last page they cover. Code blocks lose their indentation and, with
    the default engine, formulas are dropped unless it was built with ``formulas=True``.

    Parameters
    ----------
    source
        Path of a PDF file.
    engine
        Converts the PDF to HTML; defaults to :class:`DoclingEngine`.

    Raises
    ------
    ReadError
        When *source* is not a file or is over the size cap, the engine fails, or the PDF has no text.
    """
    path = Path(source)
    _check_file(path)
    root = _parse(path, _to_html(path, engine or DoclingEngine()))
    has_math = root.find(".//md-math") is not None
    chapters = split_chapters(root, path.stem)
    if not chapters:
        raise ReadError(f"{path.name} has no extractable text")
    return Document(
        DocumentMetadata(title=path.stem, source_file=path.name),
        tuple(chapters),
        has_math=has_math,
    )
