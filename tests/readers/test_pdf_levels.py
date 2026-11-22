"""Tests for matching PDF headings to outline levels."""

from types import MappingProxyType

from md_studio.readers.pdf_levels import heading_level, outline_key

OUTLINE = MappingProxyType({
    outline_key("Introduction"): 1,
    outline_key("Encoder and Decoder Stacks"): 2,
})


def test_numbered_heading_matches_unnumbered_outline_title() -> None:
    assert heading_level("1 Introduction", OUTLINE) == 1
    assert heading_level("3.1  Encoder and Decoder   Stacks", OUTLINE) == 2


def test_unlisted_heading_sits_below_the_deepest_entry() -> None:
    assert heading_level("Abstract", OUTLINE) == 3


def test_without_an_outline_every_heading_is_level_one() -> None:
    assert heading_level("Anything", {}) == 1


def test_numbering_is_only_stripped_at_the_start() -> None:
    assert outline_key("A Survey of 3.5 Models") == "a survey of 3.5 models"
