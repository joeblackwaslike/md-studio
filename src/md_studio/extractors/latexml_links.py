"""Links and image sources of a LaTeXML page: absolute URLs and heading anchors."""

from collections.abc import Iterable, Mapping

from md_studio.core.urls import safe_urlsplit
from md_studio.extractors.latexml_urls import absolute_url
from md_studio.readers.html import HtmlElement

_KEPT_SCHEMES = frozenset(("http", "https", "mailto"))
_HREF = "href"


def rewrite_links(
    links: Iterable[HtmlElement], anchors: Mapping[str, str], paper: str | None
) -> int:
    """Point each in-page link at its heading's anchor and unwrap the ones with no heading.

    Links to ``#id`` become ``#<anchor>`` when *anchors* has the id and are unwrapped to
    their text otherwise. Relative links become absolute; links with a scheme other than
    http, https or mailto (``data:``, ``javascript:``), protocol-relative links (``//host``)
    and malformed ones are unwrapped. Returns how many relative links could not be made
    absolute because the paper is unknown; they are left as they are.
    """
    return sum(_rewrite(link, anchors, paper) for link in links)


def _rewrite(link: HtmlElement, anchors: Mapping[str, str], paper: str | None) -> bool:
    target = link.get(_HREF, "")
    if target.startswith("#"):
        _point(link, anchors.get(target[1:]))
    elif _unsafe(target):
        _unwrap(link)
    else:
        return _absolutize(link, target, paper)
    return False


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
    if parts.scheme:
        return parts.scheme.lower() not in _KEPT_SCHEMES
    return bool(parts.netloc)


def _absolutize(link: HtmlElement, target: str, paper: str | None) -> bool:
    resolved = absolute_url(target, paper) if target else None
    if resolved is None:
        return bool(target)
    link.set(_HREF, resolved)
    return False
