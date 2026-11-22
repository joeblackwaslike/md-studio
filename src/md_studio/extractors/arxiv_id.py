"""Strict recognition of arXiv identifiers and arxiv.org URLs."""

import re
from urllib.parse import SplitResult, urlsplit

_NEW_STYLE = r"[0-9]{4}\.[0-9]{4,5}"
_OLD_STYLE = r"[a-z]+(?:-[a-z]+)*(?:\.[A-Z]{2})?/[0-9]{7}"
_ID = rf"(?:{_NEW_STYLE}|{_OLD_STYLE})(?:v[0-9]+)?"
_BARE = re.compile(_ID)
_PATH = re.compile(rf"/(?P<kind>abs|pdf|html)/(?P<id>{_ID})(?P<pdf>\.pdf)?/?")
_HOSTS = frozenset(("arxiv.org", "www.arxiv.org"))


def _hosted(parts: SplitResult) -> bool:
    """Return whether *parts* names arxiv.org over http(s) without a port or userinfo."""
    try:
        bare = parts.port is None and parts.username is None
    except ValueError:
        return False
    return bare and parts.scheme in {"http", "https"} and parts.hostname in _HOSTS


def _url_id(source: str) -> str | None:
    """Return the id in an ``arxiv.org`` abs, pdf or html URL, or ``None``."""
    try:
        parts = urlsplit(source)
    except ValueError:
        return None
    found = _PATH.fullmatch(parts.path)
    if found is None or not _hosted(parts):
        return None
    if found["pdf"] and found["kind"] != "pdf":
        return None
    return found["id"]


def parse_arxiv_id(source: str) -> str | None:
    """Return the arXiv id (with any version) named by *source*, or ``None``.

    Accepts ``arxiv.org`` abs, pdf and html URLs (a pdf URL may end in ``.pdf``) and bare
    ids, both new-style (``2606.24937v3``) and old-style (``hep-th/9901001``). Anything
    else, including other hosts, other paths and partial matches, gives ``None``.
    """
    if not source.isprintable() or source != source.strip():
        return None
    if "://" in source:
        return _url_id(source)
    return source if _BARE.fullmatch(source) else None
