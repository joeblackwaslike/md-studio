"""Read a local HTML file or an http(s) page into a single- or multi-chapter Document."""

from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from lxml import etree
from lxml import html as lxml_html

from md_studio.core.document import Document, DocumentMetadata, SourceChapter
from md_studio.core.exceptions import ReadError
from md_studio.readers.decode import decode_html
from md_studio.readers.source import LoadedSource, load_source

type HtmlElement = lxml_html.HtmlElement  # type: ignore[no-any-unimported]
ChapterSplitter = Callable[[HtmlElement], list[SourceChapter]]


def _parser(encoding: str | None) -> lxml_html.HTMLParser:  # type: ignore[no-any-unimported]
    return lxml_html.HTMLParser(no_network=True, remove_comments=True, encoding=encoding)


def _parse(loaded: LoadedSource) -> HtmlElement:
    text = decode_html(loaded.raw, loaded.charset)
    payload = loaded.raw if text is None else text.encode("utf-8")
    parser = _parser(None if text is None else "utf-8")
    try:
        return lxml_html.document_fromstring(payload, parser=parser)
    except (etree.ParserError, etree.XMLSyntaxError) as exc:
        raise ReadError(f"Could not parse HTML from {loaded.name}: {exc}") from exc


def _split(root: HtmlElement, splitter: ChapterSplitter) -> list[SourceChapter]:
    try:
        chapters = splitter(root)
    except Exception as exc:
        raise ReadError(f"Chapter splitter failed: {exc}") from exc
    if not chapters:
        raise ReadError("Chapter splitter returned no chapters")
    return chapters


def _fallback_title(name: str) -> str:
    if "://" not in name:
        return Path(name).stem
    parts = urlsplit(name)
    segment = parts.path.rstrip("/").rpartition("/")[2]
    return Path(segment).stem or parts.netloc


def _single_chapter(root: HtmlElement, title: str, name: str) -> SourceChapter:
    body = root.find("body")
    return SourceChapter(
        title or _fallback_title(name),
        root if body is None else body,
        title_is_fallback=not title,
    )


def _chapters(
    root: HtmlElement,
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
    loaded = load_source(source, transport)
    root = _parse(loaded)
    title = (root.findtext("head/title") or "").strip()
    chapters = _chapters(root, title, loaded.name, splitter)
    return Document(DocumentMetadata(title=title, source_file=loaded.name), tuple(chapters))
