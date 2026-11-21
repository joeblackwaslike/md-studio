"""Read a built EPUB archive into chapters and metadata for Markdown export."""
# flake8: noqa: WPS412 -- this package __init__ is a pure public-API re-export surface

from md_studio.readers.epub.document import read_epub

__all__ = ["read_epub"]
