"""Document metadata from a LaTeXML page: the title rebuilt from its parts, and the authors."""

from dataclasses import replace

from md_studio.core.document import DocumentMetadata
from md_studio.extractors.latexml_classes import classes_of
from md_studio.extractors.latexml_findings import Findings
from md_studio.extractors.latexml_text import plain_text


def rewrite_metadata(metadata: DocumentMetadata, found: Findings) -> DocumentMetadata:
    """Return *metadata* with the title rebuilt as ``Title: Subtitle`` and the page's authors."""
    authors = _authors(found) or metadata.authors
    return replace(metadata, title=_title(metadata, found), authors=authors)


def _authors(found: Findings) -> tuple[str, ...]:
    if found.authors is None:
        return ()
    names = (
        plain_text(person)
        for person in found.authors.iter("span")
        if "ltx_personname" in classes_of(person)
    )
    return tuple(name for name in names if name)


def _title(metadata: DocumentMetadata, found: Findings) -> str:
    """Rebuild the glued ``<title>`` as ``Title: Subtitle`` from the document's title elements."""
    pair = _title_pair(found)
    if pair is None or _squash(metadata.title) != "".join(pair):
        return metadata.title
    return ": ".join(pair)


def _squash(text: str) -> str:
    return " ".join(text.split())


def _title_pair(found: Findings) -> tuple[str, str] | None:
    if found.document_title is not None and found.subtitle is not None:
        return plain_text(found.document_title), plain_text(found.subtitle)
    if found.titlepage is None:
        return None
    texts = [plain_text(child) for child in found.titlepage if child.tag == "p"]
    match texts[:2]:
        case [first, second] if first and second:
            return first, second
        case _:
            return None
