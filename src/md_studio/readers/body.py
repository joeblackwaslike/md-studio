"""Bounded reading and decompression of a response body."""

from collections.abc import Iterator

import httpx

from md_studio.core.exceptions import ReadError
from md_studio.readers import limits
from md_studio.readers.deadline import Deadline
from md_studio.readers.inflate import expand

_CODINGS = ("gzip", "x-gzip", "deflate")


def _coding(response: httpx.Response) -> str | None:
    """Return the single supported content coding of *response*, or ``None`` for identity."""
    header: str = response.headers.get("content-encoding", "")
    names = [name.strip().lower() for name in header.split(",")]
    names = [name for name in names if name not in {"", "identity"}]
    if not names:
        return None
    if len(names) > 1 or names[0] not in _CODINGS:
        raise ReadError(f"Unsupported content encoding {header!r}")
    return names[0]


def _raw(response: httpx.Response) -> Iterator[bytes]:
    """Yield undecoded pieces, refusing more raw bytes than the cap."""
    total = 0
    for piece in response.iter_raw():
        total += len(piece)
        if total > limits.MAX_BYTES:
            raise ReadError(limits.TOO_BIG)
        yield piece


def read_body(response: httpx.Response, deadline: Deadline) -> bytes:
    """Read *response* with the size cap enforced on raw and decompressed bytes.

    Raises
    ------
    ReadError
        On an oversized or corrupt body, an unsupported content encoding, or an
        expired deadline.
    """
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limits.MAX_BYTES:
        raise ReadError(limits.TOO_BIG)
    payload = bytearray()
    for chunk in expand(_raw(response), _coding(response)):
        payload.extend(chunk)
        if len(payload) > limits.MAX_BYTES:
            raise ReadError(limits.TOO_BIG)
        deadline.check()
    return bytes(payload)
