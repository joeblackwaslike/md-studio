"""Read a PDF's outline and page count with pdfium, before and beside Docling."""

from contextlib import closing
from pathlib import Path

import pypdfium2

from md_studio.core.exceptions import ReadError
from md_studio.readers import limits
from md_studio.readers.pdf_levels import outline_key


def ensure_page_limit(path: Path) -> None:
    """Raise :class:`ReadError` when the PDF has more than ``limits.MAX_PAGES`` pages."""
    with closing(pypdfium2.PdfDocument(path)) as pdf:
        pages = len(pdf)
    if pages > limits.MAX_PAGES:
        raise ReadError(f"{path.name} has {pages} pages; the limit is {limits.MAX_PAGES}")


def outline_levels(path: Path) -> dict[str, int]:
    """Return outline entry titles (as :func:`outline_key`) mapped to 1-based depth.

    The first entry of a title wins.
    """
    with closing(pypdfium2.PdfDocument(path)) as pdf:
        entries = [(entry.get_title(), entry.level) for entry in pdf.get_toc()]
    return {outline_key(title): level + 1 for title, level in reversed(entries)}
