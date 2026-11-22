"""Resolving and vetting the URLs of a LaTeXML page against arXiv's HTML tree."""

from urllib.parse import urljoin

from md_studio.core.urls import safe_urlsplit
from md_studio.extractors.arxiv_id import parse_arxiv_id

HTML_ROOT = "https://arxiv.org/html/"
_WEB_SCHEMES = frozenset(("http", "https"))


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


def is_web_source(source: str) -> bool:
    """Return whether *source* is a relative path, or an http(s) URL with a host.

    Other schemes (``file:``, ``ftp:``, ``data:``), protocol-relative sources and malformed
    ones are not.
    """
    parts = safe_urlsplit(source)
    if parts is None:
        return False
    if parts.scheme:
        return parts.scheme.lower() in _WEB_SCHEMES
    return not parts.netloc
