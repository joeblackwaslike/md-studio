"""Links and image sources of a LaTeXML page: absolute URLs and heading anchors."""

from collections.abc import Iterable, Mapping
from urllib.parse import urljoin

from md_studio.core.urls import safe_urlsplit
from md_studio.extractors.arxiv_id import parse_arxiv_id
from md_studio.readers.html import HtmlElement

HTML_ROOT = "https://arxiv.org/html/"
_KEPT_SCHEMES = frozenset(("http", "https", "mailto"))
_HREF = "href"


def absolute_url(source: str, paper: str | None) -> str | None:
    """Resolve *source* against arXiv's HTML tree, or ``None`` when that needs the paper id.

    A source whose first segment is itself an arXiv id (``2606.24937v3/figures/a.png``)
    and a root-relative source resolve against ``https://arxiv.org/html/``; any other
    relative source resolves against the paper's own directory, which needs *paper*.
    Malformed and protocol-relative (``//host/x``) sources give ``None``.
    """
    parts = safe_urlsplit(source)
    if parts is None:
        return None
    if parts.scheme:
        return source
    if parts.netloc:
        return None
    first = source.split("/", 1)[0]
    if source.startswith("/") or parse_arxiv_id(first) is not None:
        return urljoin(HTML_ROOT, source)
    return None if paper is None else urljoin(f"{HTML_ROOT}{paper}/", source)


def rewrite_links(
    links: Iterable[HtmlElement], anchors: Mapping[str, str], paper: str | None
) -> None:
    """Point each in-page link at its heading's anchor and unwrap the ones with no heading.

    Links to ``#id`` become ``#<anchor>`` when *anchors* has the id and are unwrapped to
    their text otherwise. Relative links become absolute; links with a scheme other than
    http, https or mailto (``data:``, ``javascript:``) are unwrapped.
    """
    for link in links:
        target = link.get(_HREF, "")
        if target.startswith("#"):
            _point(link, anchors.get(target[1:]))
        elif _unsafe(target):
            _unwrap(link)
        else:
            _absolutize(link, target, paper)


def _point(link: HtmlElement, anchor: str | None) -> None:
    if anchor is None:
        _unwrap(link)
    else:
        link.set(_HREF, f"#{anchor}")


def _unwrap(link: HtmlElement) -> None:
    """Turn *link* into a plain span in constant time (``drop_tag`` costs its sibling count)."""
    link.attrib.clear()
    link.tag = "span"


def _unsafe(target: str) -> bool:
    parts = safe_urlsplit(target)
    if parts is None:
        return True
    return bool(parts.scheme) and parts.scheme.lower() not in _KEPT_SCHEMES


def _absolutize(link: HtmlElement, target: str, paper: str | None) -> None:
    resolved = absolute_url(target, paper) if target else None
    if resolved is not None:
        link.set(_HREF, resolved)
