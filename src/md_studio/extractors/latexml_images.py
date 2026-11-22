"""Images: absolute sources, and the caption instead of LaTeXML's placeholder alt text."""

from collections.abc import Iterable

from md_studio.extractors.latexml_findings import Image
from md_studio.extractors.latexml_text import plain_text
from md_studio.extractors.latexml_urls import absolute_url, is_web_source
from md_studio.readers.html import HtmlElement

_PLACEHOLDER_ALT = "Refer to caption"
_DATA_PREFIX = "data:"
_FALLBACK_ALT = "image"

type _Captions = dict[HtmlElement, str]


def rewrite_images(images: Iterable[Image], paper: str | None) -> int:
    """Rewrite every image and return how many sources could not be made absolute.

    ``data:`` images are dropped; any other source that is not a relative path or an
    http(s) URL loses its ``src`` and renders as its alt text. A relative source is resolved against the paper's HTML
    tree, and the "Refer to caption" alt text becomes the text of the figure's caption.
    """
    captions: _Captions = {}
    return sum(_rewrite(image, paper, captions) for image in images)


def _rewrite(image: Image, paper: str | None, captions: _Captions) -> bool:
    source = image.element.get("src", "").strip()
    if not source or source.lower().startswith(_DATA_PREFIX):
        image.element.drop_tree()
        return False
    image.element.set("alt", _alt(image, captions))
    if not is_web_source(source):
        image.element.attrib.pop("src")
        return False
    resolved = absolute_url(source, paper)
    image.element.set("src", resolved or source)
    return resolved is None


def _alt(image: Image, captions: _Captions) -> str:
    alt = image.element.get("alt", "").strip()
    if alt == _PLACEHOLDER_ALT:
        alt = _caption(image.figure, captions)
    return alt or _FALLBACK_ALT


def _caption(figure: HtmlElement | None, cache: _Captions) -> str:
    if figure is None:
        return ""
    if figure not in cache:
        caption = figure.find("figcaption")
        cache[figure] = "" if caption is None else plain_text(caption)
    return cache[figure]
