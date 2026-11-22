"""Bounded reading and decompression of a response body."""

import zlib
from collections.abc import Iterable, Iterator

import httpx

from md_studio.core.exceptions import ReadError
from md_studio.readers import limits
from md_studio.readers.deadline import Deadline

_GZIP_WBITS = 47
_RAW_WBITS = -15
_ZLIB_WBITS = 15
_CM_MASK = 15
_CM_DEFLATE = 8
_FCHECK_MODULUS = 31
_OUTPUT_STEP = 65_536
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


def _wbits(coding: str, head: bytes) -> int:
    if coding != "deflate":
        return _GZIP_WBITS
    prefix = int.from_bytes(head[:2], "big")
    method = head[0] & _CM_MASK if head else 0
    valid = method == _CM_DEFLATE and prefix % _FCHECK_MODULUS == 0
    return _ZLIB_WBITS if valid else _RAW_WBITS


def _step(inflater: "zlib._Decompress", pending: bytes) -> bytes:
    try:
        return inflater.decompress(pending, _OUTPUT_STEP)
    except zlib.error:
        raise ReadError("Corrupt compressed response body") from None


def _raw(response: httpx.Response) -> Iterator[bytes]:
    """Yield undecoded pieces, refusing more raw bytes than the cap."""
    total = 0
    for piece in response.iter_raw():
        total += len(piece)
        if total > limits.MAX_BYTES:
            raise ReadError(limits.TOO_BIG)
        yield piece


def _expand(pieces: Iterable[bytes], coding: str | None) -> Iterator[bytes]:
    """Yield decoded output in steps of at most ``_OUTPUT_STEP`` bytes."""
    if coding is None:
        yield from pieces
        return
    inflater = None
    for piece in pieces:
        inflater = inflater or zlib.decompressobj(_wbits(coding, piece))
        pending = piece
        while pending:
            yield _step(inflater, pending)
            pending = inflater.unconsumed_tail


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
    for chunk in _expand(_raw(response), _coding(response)):
        payload.extend(chunk)
        if len(payload) > limits.MAX_BYTES:
            raise ReadError(limits.TOO_BIG)
        deadline.check()
    return bytes(payload)
