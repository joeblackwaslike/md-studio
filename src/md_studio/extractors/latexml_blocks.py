"""Listings and equations: each is replaced by a block, in document order."""

from collections.abc import Iterable

from md_studio.extractors.latexml_classes import classes_of
from md_studio.extractors.latexml_code import listing_block
from md_studio.extractors.latexml_math import equation_block
from md_studio.extractors.latexml_place import Placer
from md_studio.readers.html import HtmlElement


def rewrite_blocks(blocks: Iterable[HtmlElement]) -> bool:
    """Replace each listing by ``pre`` and each equation by display math; report any math.

    The blocks are handled in document order, so ones hoisted out of the same paragraph
    keep their order.
    """
    placer = Placer()
    has_math = False
    for old in blocks:
        if "ltx_listing" in classes_of(old):
            placer.place(old, listing_block(old))
            continue
        block = equation_block(old)
        if block is None:
            old.drop_tree()
        else:
            has_math = True
            placer.place(old, block)
    placer.finish()
    return has_math
