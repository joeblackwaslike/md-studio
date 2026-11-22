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
_GZIP_MAGIC = b"\x1f\x8b"
_TRUNCATED = "Compressed response body is truncated"


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
    """Yield everything *chunk* decodes to, including output left pending by the step cap."""
    pending = chunk
    while pending:
        yield _step(inflater, pending)
        pending = b"" if inflater.eof else inflater.unconsumed_tail
    yield from iter(partial(_step, inflater, b""), b"")


class _Decoder:
    """Decode one deflate stream, or every concatenated member of a gzip stream."""

    def __init__(self, coding: str) -> None:
        self._coding = coding
        self._carry = bytearray()
        self._inflater: zlib._Decompress | None = None
        self._ignoring = False

    def feed(self, chunk: bytes) -> Iterator[bytes]:
        """Yield decoded output for the next raw *chunk*."""
        if not self._ignoring:
            self._carry.extend(chunk)
        while self._carry and not self._ignoring:
            inflater = self._active()
            if inflater is None:
                break
            pending = bytes(self._carry)
            self._carry.clear()
            yield from _feed(inflater, pending)
            if inflater.eof:
                self._carry.extend(inflater.unused_data)

    def finish(self) -> None:
        """Require the last member to have ended; bytes left after it are padding or junk."""
        inflater = self._inflater
        if inflater is None and self._carry:
            raise ReadError(_TRUNCATED)
        if inflater is not None and not inflater.eof:
            raise ReadError(_TRUNCATED)
        if bytes(self._carry).lstrip(b"\0") == _GZIP_MAGIC[:1]:
            raise ReadError(_TRUNCATED)

    def _active(self) -> "zlib._Decompress | None":
        """Return the inflater ``_carry`` should be fed to, starting a member if needed."""
        if self._inflater is not None and not self._inflater.eof:
            return self._inflater
        finished = self._inflater is not None
        if finished and self._coding == "deflate":
            self._stop()
            return None
        if finished:
            self._carry = bytearray(bytes(self._carry).lstrip(b"\0"))
        head = bytes(self._carry[:_SNIFF_BYTES])
        if len(head) < _SNIFF_BYTES:
            return None
        if finished and head != _GZIP_MAGIC:
            self._stop()
            return None
        if self._inflater is None or finished:
            self._inflater = zlib.decompressobj(_wbits(self._coding, head))
        return self._inflater

    def _stop(self) -> None:
        self._ignoring = True
        self._carry.clear()


def expand(pieces: Iterable[bytes], coding: str | None) -> Iterator[bytes]:
    """Yield decoded output in steps of at most ``_OUTPUT_STEP`` bytes.

    The format is chosen once two bytes have arrived. Gzip members are decoded one
    after another, zero padding after the last is tolerated, and any other bytes after
    a complete member are ignored. Deflate is a single stream.
    """
    if coding is None:
        yield from pieces
        return
    decoder = _Decoder(coding)
    for piece in pieces:
        yield from decoder.feed(piece)
    decoder.finish()
