"""Chunk-boundary properties of the incremental decompressor."""

import gzip
import itertools
import random
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from types import MappingProxyType

import pytest

from md_studio.core.exceptions import ReadError
from md_studio.readers.inflate import expand

STEP = 65_536
PLAINS = (
    b"x",
    b"ab",
    b"abc",
    b"<p>hello world</p>" * 7,
    b"y" * STEP,
    b"z" * (STEP + 1),
    b"w" * (STEP * 2),
)
SPLITS_PER_BODY = 50
TRUNCATABLE = b"<p>truncate me please</p>" * 3
SEED = 20260521


def _raw_deflate(payload: bytes) -> bytes:
    compressor = zlib.compressobj(wbits=-15)
    return compressor.compress(payload) + compressor.flush()


def _member_parts(payload: bytes) -> list[bytes]:
    third = max(len(payload) // 3, 1)
    return [payload[:third], payload[third : third * 2], payload[third * 2 :]]


def _three_members(payload: bytes) -> bytes:
    return b"".join(gzip.compress(part) for part in _member_parts(payload))


@dataclass(frozen=True, slots=True)
class Variant:
    coding: str
    encode: Callable[[bytes], bytes]


def _padded(payload: bytes) -> bytes:
    return b"".join([gzip.compress(payload), bytes(5)])


def _padded_three(payload: bytes) -> bytes:
    return b"".join([_three_members(payload), bytes(3)])


def _junked(payload: bytes) -> bytes:
    return b"".join([gzip.compress(payload), b"junk!"])


VARIANTS = MappingProxyType({
    "gzip": Variant("gzip", gzip.compress),
    "gzip3": Variant("gzip", _three_members),
    "gzip-padded": Variant("gzip", _padded),
    "gzip3-padded": Variant("gzip", _padded_three),
    "gzip-junk": Variant("gzip", _junked),
    "zlib": Variant("deflate", zlib.compress),
    "raw": Variant("deflate", _raw_deflate),
})


def _fixed(body: bytes, size: int) -> list[bytes]:
    return [body[at : at + size] for at in range(0, len(body), size)] or [b""]


def _random_split(body: bytes, rng: random.Random) -> list[bytes]:
    cuts = sorted(rng.sample(range(len(body) + 1), k=min(len(body) + 1, rng.randint(1, 8))))
    edges = [0, *cuts, len(body)]
    return [body[start:stop] for start, stop in itertools.pairwise(edges)]


def _chunkings(body: bytes) -> Iterator[list[bytes]]:
    for size in (1, 2, 3, 7, 64, max(len(body), 1)):
        yield _fixed(body, size)
    rng = random.Random(SEED)
    for _ in range(SPLITS_PER_BODY):
        yield _random_split(body, rng)


def _decoded(pieces: list[bytes], coding: str) -> bytes:
    return b"".join(expand(pieces, coding))


@pytest.mark.parametrize("name", sorted(VARIANTS))
@pytest.mark.parametrize("plain", PLAINS, ids=lambda plain: f"{len(plain)}b")
def test_any_chunking_decodes_to_the_original(name: str, plain: bytes) -> None:
    variant = VARIANTS[name]
    body = variant.encode(plain)

    for pieces in _chunkings(body):
        assert _decoded(pieces, variant.coding) == plain


def _boundaries(plain: bytes, name: str) -> set[int]:
    if name != "gzip3":
        return {0}
    sizes = [len(gzip.compress(part)) for part in _member_parts(plain)]
    return {sum(sizes[:count]) for count in range(len(sizes))}


@pytest.mark.parametrize("name", ["gzip", "gzip3", "zlib", "raw"])
def test_every_truncation_is_rejected_unless_it_ends_a_complete_member(name: str) -> None:
    variant = VARIANTS[name]
    body = variant.encode(TRUNCATABLE)
    complete = _boundaries(TRUNCATABLE, name)

    for cut, _byte in enumerate(body):
        if cut in complete:
            _decoded([body[:cut]], variant.coding)
            continue
        with pytest.raises(ReadError, match="truncated"):
            _decoded([body[:cut]], variant.coding)


def test_odd_length_body_ending_in_a_single_byte_piece_decodes() -> None:
    body = gzip.compress(b"<p>odd</p>")
    if len(body) % 2 == 0:
        body = gzip.compress(b"<p>odds</p>")

    assert _decoded(_fixed(body, 2), "gzip").startswith(b"<p>odd")


def test_output_ending_exactly_on_the_step_is_not_lost_with_a_following_member() -> None:
    body = b"".join([gzip.compress(b"a" * STEP), gzip.compress(b"b")])

    assert _decoded([body], "gzip") == b"".join([b"a" * STEP, b"b"])


def test_junk_after_a_member_is_not_mistaken_for_a_truncated_header() -> None:
    pieces = [b"".join([gzip.compress(b"ok"), b"zz"]), b"\x1f"]

    assert _decoded(pieces, "gzip") == b"ok"


def test_junk_split_around_zero_padding_is_ignored() -> None:
    pieces = [gzip.compress(b"ok"), bytes(3), b"\x00", b"j"]

    assert _decoded(pieces, "gzip") == b"ok"
