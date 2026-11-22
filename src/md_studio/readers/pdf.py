"""Read a PDF into a chapter-split Document through a pluggable PDF engine."""

from pathlib import Path
from tempfile import TemporaryDirectory

from lxml import etree
from lxml import html as lxml_html

from md_studio.core.document import Document, DocumentMetadata
from md_studio.core.exceptions import ReadError
from md_studio.readers.pdf_chapters import split_chapters
from md_studio.readers.pdf_engines import DoclingEngine, PdfEngine


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
        When *source* is not a file, the engine fails, or the PDF has no text.
    """
    path = Path(source)
    if not path.is_file():
        raise ReadError(f"Could not read {path}: not a file")
    with TemporaryDirectory() as images_dir:
        html = (engine or DoclingEngine()).to_html(path, Path(images_dir))
    try:
        root = lxml_html.document_fromstring(html)
    except (etree.ParserError, etree.XMLSyntaxError) as exc:
        raise ReadError(f"Could not parse the converted text of {path.name}: {exc}") from exc
    chapters = split_chapters(root, path.stem)
    if not chapters:
        raise ReadError(f"{path.name} has no extractable text")
    return Document(
        DocumentMetadata(title=path.stem, source_file=path.name),
        tuple(chapters),
        has_math=root.find(".//md-math") is not None,
    )
