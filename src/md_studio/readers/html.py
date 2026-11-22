"""Read a local HTML file or an http(s) page into a single- or multi-chapter Document."""

from collections.abc import Callable
from pathlib import Path

import httpx
from lxml import etree
from lxml import html as lxml_html

from md_studio.core.document import Document, DocumentMetadata, SourceChapter
from md_studio.core.exceptions import ReadError
from md_studio.readers.source import load_source

ChapterSplitter = Callable[[lxml_html.HtmlElement], list[SourceChapter]]  # type: ignore[no-any-unimported]


def _parse(raw: bytes, name: str) -> etree._Element:  # type: ignore[no-any-unimported]
    parser = lxml_html.HTMLParser(no_network=True, remove_comments=True)
    try:
        root = lxml_html.document_fromstring(raw, parser=parser)
    except (etree.ParserError, etree.XMLSyntaxError) as exc:
        raise ReadError(f"Could not parse HTML from {name}: {exc}") from exc
    return root


def _split(root: etree._Element, splitter: ChapterSplitter) -> list[SourceChapter]:  # type: ignore[no-any-unimported]
    try:
        chapters = splitter(root)
    except Exception as exc:
        raise ReadError(f"Chapter splitter failed: {exc}") from exc
    if not chapters:
        raise ReadError("Chapter splitter returned no chapters")
    return chapters


def _single_chapter(root: lxml_html.HtmlElement, title: str, name: str) -> SourceChapter:  # type: ignore[no-any-unimported]
    body = root.find("body")
    return SourceChapter(
        title or Path(name).stem,
        root if body is None else body,
        title_is_fallback=not title,
    )


def _chapters(  # type: ignore[no-any-unimported]
    root: lxml_html.HtmlElement,
    title: str,
    name: str,
    splitter: ChapterSplitter | None,
) -> list[SourceChapter]:
    if splitter is None:
        return [_single_chapter(root, title, name)]
    return _split(root, splitter)


def read_html(
    source: Path | str,
    *,
    splitter: ChapterSplitter | None = None,
    transport: httpx.BaseTransport | None = None,
) -> Document:
    """Read an HTML file or http(s) URL into a :class:`Document`.

    Parameters
    ----------
    source
        Local path, or an ``http``/``https`` URL fetched with a size and time cap.
    splitter
        Turns the parsed tree into chapters. Without one the whole body is a
        single chapter titled after the page ``<title>``.
    transport
        Optional httpx transport, used by tests to avoid the network.

    Raises
    ------
    ReadError
        On an unsupported scheme, fetch or read failure, oversize input, unparseable
        HTML, or a splitter that fails or yields no chapters.
    """
    raw, name = load_source(source, transport)
    root = _parse(raw, name)
    title = (root.findtext(".//title") or "").strip()
    chapters = _chapters(root, title, name, splitter)
    return Document(DocumentMetadata(title=title, source_file=name), tuple(chapters))
