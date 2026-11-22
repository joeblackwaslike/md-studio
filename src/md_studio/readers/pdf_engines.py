"""PDF engines: the protocol the PDF reader calls, and the Docling implementation."""

import logging
from pathlib import Path
from typing import Protocol

from md_studio.core.exceptions import ReadError

_LOG = logging.getLogger(__name__)
_MISSING = "PDF support needs Docling; install it with: pip install 'md-studio[pdf]'"
_SLOW_FORMULAS = "Formula enrichment is on; Docling spends about 47 seconds per formula"


class PdfEngine(Protocol):
    """Turns a PDF into HTML the PDF reader can split into chapters."""

    def to_html(self, path: Path, images_dir: Path) -> str:
        """Return HTML for *path*: flat top-level blocks, each with a ``data-page`` attribute.

        Headings are ``h1`` to ``h6`` by outline depth, display math is
        ``<md-math display="block" tex="...">``, and pictures are written into *images_dir*.
        """


class DoclingEngine:
    """Converts PDFs with Docling, which is imported only when the first PDF is read.

    Parameters
    ----------
    formulas
        Decode formulas as LaTeX. Off by default because it costs about 47 seconds per
        formula on an Apple M1 Max; with it off formulas are dropped.
    """

    def __init__(self, *, formulas: bool = False) -> None:
        """Choose whether formula enrichment runs."""
        self._formulas = formulas

    def to_html(self, path: Path, images_dir: Path) -> str:
        """Convert *path* with Docling and render its items as page-tagged HTML.

        Raises
        ------
        ReadError
            When Docling is not installed.
        """
        try:
            from md_studio.readers.pdf_docling import convert_pdf  # noqa: PLC0415
        except ImportError:
            raise ReadError(_MISSING) from None
        if self._formulas:
            _LOG.warning(_SLOW_FORMULAS)
        return convert_pdf(path, images_dir, formulas=self._formulas)
