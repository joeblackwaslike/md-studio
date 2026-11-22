"""Size- and time-capped loading of an HTML source from a URL or local file."""

from dataclasses import dataclass
from pathlib import Path

import httpx

from md_studio.core.exceptions import ReadError
from md_studio.readers.deadline import Deadline
from md_studio.readers.redirects import open_final
from md_studio.readers.urls import display_url, url_scheme

MAX_BYTES = 52_428_800
_SCHEMES = ("http", "https")
_TOO_BIG = "HTML source exceeds the size cap"


@dataclass(frozen=True, slots=True)
class LoadedSource:
    """Raw bytes of a source, a credential-free display name, and any declared charset."""

    raw: bytes
    name: str
    charset: str | None = None


def _drain(response: httpx.Response, deadline: Deadline) -> bytes:
    """Read the decoded body of *response*, enforcing the size cap and total deadline."""
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BYTES:
        raise ReadError(_TOO_BIG)
    payload = bytearray()
    for piece in response.iter_bytes():
        payload.extend(piece)
        if len(payload) > MAX_BYTES:
            raise ReadError(_TOO_BIG)
        deadline.check()
    return bytes(payload)


def _failure(name: str, exc: httpx.HTTPError | httpx.InvalidURL) -> ReadError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return ReadError(f"Could not fetch {name}: HTTP {status}")
    return ReadError(f"Could not fetch {name}: {type(exc).__name__}")


def _fetch(url: str, transport: httpx.BaseTransport | None) -> LoadedSource:
    """Stream *url* into memory, enforcing the size cap and total deadline."""
    name = display_url(url)
    deadline = Deadline()
    try:
        with open_final(url, transport, deadline) as response:
            response.raise_for_status()
            raw = _drain(response, deadline)
            return LoadedSource(raw, name, response.charset_encoding)
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        raise _failure(name, exc) from exc


def _read_file(path: Path) -> LoadedSource:
    """Read *path* with the same size cap as network fetches."""
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise ReadError(f"Could not read {path}: {exc}") from exc
    if len(payload) > MAX_BYTES:
        raise ReadError(_TOO_BIG)
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
