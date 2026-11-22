"""Size- and time-capped loading of an HTML source from a URL or local file."""

from pathlib import Path
from urllib.parse import urlsplit

import httpx

from md_studio.core.exceptions import ReadError

MAX_BYTES = 52_428_800
TIMEOUT_SECONDS = 30.0
MAX_REDIRECTS = 3
_SCHEMES = ("http", "https")
_CHUNK = 65_536


def _too_big() -> ReadError:
    return ReadError(f"HTML source exceeds {MAX_BYTES} bytes")


def _fetch(url: str, transport: httpx.BaseTransport | None) -> bytes:
    """Stream *url* into memory, enforcing the size cap on bytes actually read."""
    try:
        with (
            httpx.Client(
                timeout=TIMEOUT_SECONDS,
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                transport=transport,
            ) as client,
            client.stream("GET", url) as response,
        ):
            response.raise_for_status()
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_BYTES:
                raise _too_big()
            payload = bytearray()
            for chunk in response.iter_bytes(_CHUNK):
                payload.extend(chunk)
                if len(payload) > MAX_BYTES:
                    raise _too_big()
            return bytes(payload)
    except httpx.HTTPError as exc:
        raise ReadError(f"Could not fetch {url}: {exc}") from exc


def _read_file(path: Path) -> bytes:
    """Read *path* with the same size cap as network fetches."""
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        raise ReadError(f"Could not read {path}: {exc}") from exc
    if len(payload) > MAX_BYTES:
        raise _too_big()
    return payload


def load_source(source: Path | str, transport: httpx.BaseTransport | None) -> tuple[bytes, str]:
    """Return the raw bytes and display name of an http(s) URL or local file.

    Raises
    ------
    ReadError
        On an unsupported scheme, fetch or read failure, or input over ``MAX_BYTES``.
    """
    text = str(source)
    scheme = urlsplit(text).scheme.lower() if isinstance(source, str) else ""
    if scheme in _SCHEMES:
        return _fetch(text, transport), text
    if "://" in text:
        raise ReadError(f"Unsupported URL scheme {scheme!r}; only http and https are allowed")
    path = Path(source)
    return _read_file(path), path.name
