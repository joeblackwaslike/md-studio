"""Listings and equations: each is replaced by a block, in document order."""

from collections.abc import Iterable
from typing import NamedTuple

from md_studio.extractors.latexml_classes import classes_of
from md_studio.extractors.latexml_code import listing_block
from md_studio.extractors.latexml_math import equation_block
from md_studio.extractors.latexml_place import Placer
from md_studio.readers.html import HtmlElement


class Rewritten(NamedTuple):
    """What rewriting a block gave: whether it became math, and its missing-TeX count."""

    has_math: bool
    missing: int


def rewrite_blocks(blocks: Iterable[HtmlElement]) -> Rewritten:
    """Replace each listing by ``pre`` and each equation by display math.

    Reports whether any equation became math, and how many of their ``<math>`` had no
    ``alttext``. The blocks are handled in document order, so ones hoisted out of the same
    paragraph keep their order.
    """
    placer = Placer()
    outcomes = [_rewrite(old, placer) for old in blocks]
    placer.finish()
    return Rewritten(
        any(outcome.has_math for outcome in outcomes),
        sum(outcome.missing for outcome in outcomes),
    )


def _rewrite(old: HtmlElement, placer: Placer) -> Rewritten:
    if "ltx_listing" in classes_of(old):
        placer.place(old, listing_block(old))
        return Rewritten(has_math=False, missing=0)
    block, absent = equation_block(old)
    if block is None:
        old.drop_tree()
    else:
        placer.place(old, block)
    return Rewritten(has_math=block is not None, missing=absent)
