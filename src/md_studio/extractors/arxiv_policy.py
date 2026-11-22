"""The arxiv.org URL allowlist: only plain https ``/html/``, ``/abs/`` and ``/pdf/`` paths."""

import re

import httpx

from md_studio.readers.urls import display_url

_HOST = "arxiv.org"
_PATH = re.compile(r"/(?:html|abs|pdf)(?:/[A-Za-z0-9._-]+)+")


class ForbiddenUrlError(ValueError):
    """Raised for any URL outside ``https://arxiv.org/{html,abs,pdf}/...``."""


def _plain(url: httpx.URL) -> bool:
    """Return whether *url* is https on arxiv.org with no port, userinfo, query or fragment."""
    extras = (url.userinfo, url.query, url.fragment)
    onsite = url.scheme == "https" and url.host == _HOST
    return onsite and url.port is None and not any(extras)


def _allowed_path(url: httpx.URL) -> bool:
    """Return whether the path of *url* is a clean ``/html/``, ``/abs/`` or ``/pdf/`` path."""
    path = url.raw_path.decode("ascii", errors="replace")
    return _PATH.fullmatch(path) is not None and all(
        segment.strip(".") for segment in path.split("/")[1:]
    )


def _allowed(url: httpx.URL) -> bool:
    return _plain(url) and _allowed_path(url)


def _verdict(url: httpx.URL | str) -> tuple[bool, str]:
    parsed = httpx.URL(url) if isinstance(url, str) else url
    return _allowed(parsed), display_url(str(parsed))


def check_url(url: httpx.URL | str) -> None:
    """Raise :class:`ForbiddenUrlError` unless *url* may be fetched from arXiv.

    Only ``/html/``, ``/abs/`` and ``/pdf/`` on ``https://arxiv.org`` pass: no
    ``/e-print`` or ``/src``, no query, no userinfo, no other host or port.
    """
    try:
        allowed, shown = _verdict(url)
    except (httpx.InvalidURL, ValueError):
        raise ForbiddenUrlError("Malformed URL is not allowed") from None
    if not allowed:
        msg = f"Fetching {shown} is not allowed; only arxiv.org /html/, /abs/ and /pdf/ are"
        raise ForbiddenUrlError(msg)
