"""Read a PDF's outline, since Docling emits every heading at one level."""

from contextlib import closing
from pathlib import Path

import pypdfium2

from md_studio.readers.pdf_levels import outline_key


def outline_levels(path: Path) -> dict[str, int]:
    """Return outline entry titles (as :func:`outline_key`) mapped to 1-based depth.

    The first entry of a title wins.
    """
    with closing(pypdfium2.PdfDocument(path)) as pdf:
        entries = [(entry.get_title(), entry.level) for entry in pdf.get_toc()]
    return {outline_key(title): level + 1 for title, level in reversed(entries)}
