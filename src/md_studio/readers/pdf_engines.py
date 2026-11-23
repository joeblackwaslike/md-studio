"""PDF engines: the protocol the PDF reader calls, and the Docling implementation."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from md_studio.core.exceptions import ReadError

_LOG = logging.getLogger(__name__)
_MISSING = "PDF support needs Docling; install it with: pip install 'md-studio[pdf]'"
_SLOW_FORMULAS = "Formula enrichment is on; Docling spends about 47 seconds per formula"
_DEPENDENCIES = frozenset(("docling", "docling_core", "pypdfium2"))


class PdfEngine(Protocol):
    """Turns a PDF into HTML the PDF reader can split into chapters."""

    def to_html(self, path: Path, images_dir: Path) -> str:
        """Return HTML for *path*: flat top-level blocks, each with a ``data-page`` attribute.

        A block that spans pages carries its first page in ``data-page`` and, when different,
        its last in ``data-page-end``. Headings are ``h1`` to ``h6`` by outline depth and display math is
        ``<md-math display="block" tex="...">``. *images_dir* is scratch space for engines
        that extract pictures; the Docling engine does not use it, and pictures are rendered
        as their caption text only.
        """


def _load() -> Callable[..., str]:
    from md_studio.readers.pdf_docling import convert_pdf  # noqa: PLC0415

    return convert_pdf


def _is_dependency(name: str | None) -> bool:
    return name is not None and name.partition(".")[0] in _DEPENDENCIES


def _loaded() -> Callable[..., str]:
    try:
        return _load()
    except ModuleNotFoundError as error:
        if not _is_dependency(error.name):
            raise
        raise ReadError(_MISSING) from None


def _run(convert: Callable[..., str], path: Path, *, formulas: bool) -> str:
    try:
        return convert(path, formulas=formulas)
    except ReadError:
        raise
    except Exception as error:
        raise ReadError(f"Could not convert {path.name}: {error}") from error


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
            When Docling or one of its dependencies is not installed, or the conversion
            fails for any reason (damaged, encrypted or non-PDF input, too many pages).
        """
        convert = _loaded()
        if self._formulas:
            _LOG.warning(_SLOW_FORMULAS)
        return _run(convert, path, formulas=self._formulas)
