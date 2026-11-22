"""The arXiv LaTeXML source fix: turns a paper's HTML page into chapters the extractor reads.

arXiv serves papers as LaTeXML output, whose markup the generic HTML extractor would flatten
or mangle (equation tables, ``lstlisting`` divs, footnote spans, ``ltx_`` classes, ``data:``
download links). This fix runs on the lxml tree before extraction and rewrites those idioms
into shapes the extractor already understands, in a single scan of the page followed by one
rewrite per construct, so its cost is linear in the size of the page.
"""

from copy import deepcopy
from dataclasses import replace
from typing import ClassVar, cast

from md_studio.core.document import Document, SourceChapter
from md_studio.extractors.arxiv_id import parse_arxiv_id
from md_studio.extractors.latexml_anchors import anchors
from md_studio.extractors.latexml_blocks import rewrite_blocks
from md_studio.extractors.latexml_demote import demote_headings
from md_studio.extractors.latexml_findings import Findings
from md_studio.extractors.latexml_headings import set_entry_titles
from md_studio.extractors.latexml_images import rewrite_images
from md_studio.extractors.latexml_links import rewrite_links
from md_studio.extractors.latexml_math import rewrite_math
from md_studio.extractors.latexml_meta import rewrite_metadata
from md_studio.extractors.latexml_notes import rewrite_footnotes
from md_studio.extractors.latexml_scan import MAX_ELEMENTS, check_size, scan
from md_studio.readers.html import HtmlElement

NOT_LATEXML = "arxiv-latexml: no LaTeXML chapters found; the page was left as it is"
RELATIVE_IMAGES = (
    "arxiv-latexml: some image sources could not be made absolute and were left as they are"
)
RELATIVE_LINKS = "arxiv-latexml: some relative links could not be made absolute (paper id unknown)"


class LatexmlFix:
    """Split a LaTeXML page into chapters and rewrite its markup for extraction.

    Chapters are ``ltx_chapter``, ``ltx_appendix`` and ``ltx_bibliography`` sections, with
    part-prefixed titles; the contents list, listings, footnotes, images, math and
    cross-references are rewritten as described in each helper module.

    Parameters
    ----------
    max_elements
        Pages with more elements than this are rejected, so a hostile page cannot take
        minutes to scan.
    """

    name: ClassVar[str] = "arxiv-latexml"

    def __init__(self, max_elements: int = MAX_ELEMENTS) -> None:
        """Reject pages above *max_elements* elements."""
        self._max_elements = max_elements

    def apply(self, document: Document) -> Document:
        """Return *document* rebuilt as one chapter per LaTeXML chapter, leaving the input intact.

        A page with no LaTeXML chapters is returned unchanged with a warning.

        Raises
        ------
        ReadError
            When the page has too many elements or nests headings inside headings.
        """
        if len(document.chapters) != 1:
            return replace(document, warnings=(*document.warnings, NOT_LATEXML))
        original = cast(HtmlElement, document.chapters[0].element)
        check_size(original, self._max_elements)
        root = cast(HtmlElement, deepcopy(original))
        found = scan(root, self._max_elements)
        if not found.entries:
            return replace(document, warnings=(*document.warnings, NOT_LATEXML))
        return _rewrite(document, found)


def _rewrite(document: Document, found: Findings) -> Document:
    paper = parse_arxiv_id(document.metadata.source_file)
    images, links, has_equations = _rewrite_markup(found, paper)
    return replace(
        document,
        metadata=rewrite_metadata(document.metadata, found),
        chapters=tuple(SourceChapter(entry.title, entry.element) for entry in found.entries),
        has_math=document.has_math or bool(found.maths) or has_equations,
        embed_images=True,
        warnings=(*document.warnings, *_notes(images=images, links=links)),
    )


def _notes(*, images: int, links: int) -> list[str]:
    notes = [RELATIVE_IMAGES] if images else []
    return [*notes, RELATIVE_LINKS] if links else notes


def _rewrite_markup(found: Findings, paper: str | None) -> tuple[int, int, bool]:
    """Rewrite every construct the scan found, in an order that keeps titles and anchors right.

    Returns how many image sources and links stayed relative, and whether any equation became
    math.
    """
    set_entry_titles(found.entries)
    targets = anchors(found)
    for dropped in found.dropped:
        dropped.drop_tree()
    has_equations = rewrite_blocks(found.blocks)
    rewrite_footnotes(found.notes)
    rewrite_math(found.maths)
    images = rewrite_images(found.images, paper)
    demote_headings(found.headings, found.entry_depth)
    return images, rewrite_links(found.links, targets, paper), has_equations
