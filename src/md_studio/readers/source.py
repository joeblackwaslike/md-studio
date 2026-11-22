"""Size- and time-capped loading of an HTML source from a URL or local file."""

from dataclasses import dataclass
from pathlib import Path

import httpx

from md_studio.core.exceptions import FetchStatusError, ReadError
from md_studio.readers import limits
from md_studio.readers.body import read_body
from md_studio.readers.deadline import MESSAGE, Deadline
from md_studio.readers.redirects import open_final
from md_studio.readers.urls import display_url, url_scheme

_SCHEMES = ("http", "https")


@dataclass(frozen=True, slots=True)
class LoadedSource:
    """Raw bytes of a source, a credential-free display name, and any declared charset."""

    raw: bytes
    name: str
    charset: str | None = None


def _failure(name: str, exc: httpx.HTTPError | httpx.InvalidURL | httpx.StreamError) -> ReadError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return FetchStatusError(f"Could not fetch {name}: HTTP {status}", status)
    return ReadError(f"Could not fetch {name}: {type(exc).__name__}")


def _fetch(url: str, transport: httpx.BaseTransport | None) -> LoadedSource:
    """Stream *url* into memory, enforcing the size cap and total deadline."""
    name = display_url(url)
    deadline = Deadline()
    try:
        with open_final(url, transport, deadline) as response:
            response.raise_for_status()
            raw = read_body(response, deadline)
            return LoadedSource(raw, name, response.charset_encoding)
    except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError) as exc:
        if deadline.expired:
            raise ReadError(MESSAGE) from None
        raise _failure(name, exc) from None


def _read_file(path: Path) -> LoadedSource:
    """Read *path* with the same size cap as network fetches."""
    try:
        with path.open("rb") as stream:
            payload = stream.read(limits.MAX_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise ReadError(f"Could not read {path}: {exc}") from exc
    if len(payload) > limits.MAX_BYTES:
        raise ReadError(limits.TOO_BIG)
    return LoadedSource(payload, path.name)


def load_source(source: Path | str, transport: httpx.BaseTransport | None) -> LoadedSource:
    """Load an http(s) URL or local file.

    Raises
    ------
    ReadError
        On an unsupported scheme, fetch or read failure, or input over ``MAX_BYTES``.
    """
    scheme = url_scheme(source)
    if scheme in _SCHEMES:
        return _fetch(str(source), transport)
    if "://" in str(source):
        raise ReadError(f"Unsupported URL scheme {scheme!r}; use http or https")
    return _read_file(Path(source))
