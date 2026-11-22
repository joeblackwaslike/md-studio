"""Incremental, size-bounded decompression of gzip and deflate response bodies."""

import zlib
from collections.abc import Iterable, Iterator
from functools import partial

from md_studio.core.exceptions import ReadError

_GZIP_WBITS = 47
_RAW_WBITS = -15
_ZLIB_WBITS = 15
_CM_MASK = 15
_CM_DEFLATE = 8
_FCHECK_MODULUS = 31
_OUTPUT_STEP = 65_536
_SNIFF_BYTES = 2


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


def _feed(inflater: "zlib._Decompress", chunk: bytes) -> Iterator[bytes]:
    pending = chunk
    while pending:
        yield _step(inflater, pending)
        pending = inflater.unconsumed_tail


def _finish(inflater: "zlib._Decompress") -> Iterator[bytes]:
    """Drain output still pending after the last piece, then require a complete stream."""
    yield from iter(partial(_step, inflater, b""), b"")
    if not inflater.eof:
        raise ReadError("Compressed response body is truncated")


def expand(pieces: Iterable[bytes], coding: str | None) -> Iterator[bytes]:
    """Yield decoded output in steps of at most ``_OUTPUT_STEP`` bytes.

    The format is chosen once two bytes have arrived. Bytes after the end of the
    compressed stream, including further gzip members, are ignored.
    """
    if coding is None:
        yield from pieces
        return
    head = bytearray()
    inflater = None
    for piece in pieces:
        if inflater is not None:
            yield from _feed(inflater, piece)
            continue
        head.extend(piece)
        if len(head) >= _SNIFF_BYTES:
            inflater = zlib.decompressobj(_wbits(coding, bytes(head)))
            yield from _feed(inflater, bytes(head))
    if inflater is None and head:
        raise ReadError("Compressed response body is truncated")
    if inflater is not None:
        yield from _finish(inflater)
