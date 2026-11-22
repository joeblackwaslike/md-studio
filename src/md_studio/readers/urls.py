"""URL helpers that keep credentials and query strings out of names and messages."""

from pathlib import Path
from urllib.parse import urlsplit

from md_studio.core.exceptions import ReadError


def display_url(url: str) -> str:
    """Return *url* without userinfo, query or fragment (``scheme://host[:port]/path``)."""
    parts = urlsplit(url)
    host = parts.netloc.rpartition("@")[2]
    return parts._replace(netloc=host, query="", fragment="").geturl()


def url_scheme(source: Path | str) -> str:
    """Return the lowercase URL scheme of *source*, or ``""`` for a path.

    Raises
    ------
    ReadError
        When *source* is a string that cannot be split as a URL.
    """
    if not isinstance(source, str):
        return ""
    try:
        return urlsplit(source).scheme.lower()
    except ValueError:
        raise ReadError("Malformed URL") from None
