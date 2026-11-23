"""Tests for the two-pass padded YAML front matter."""

import pytest

from md_studio.core import ir
from md_studio.core.exceptions import OffsetOverflowError
from md_studio.core.frontmatter import (
    NUMERIC_WIDTH,
    ChapterRange,
    build,
    pad_number,
    render,
    yaml_inline_string,
)
from md_studio.core.render import ChapterOffset

_TEST_LARGE_NUMBER = 123456
_TEST_BYTE_OFFSET = 40


def _meta() -> ir.BookMeta:
    return ir.BookMeta(title="Book", authors=("A",), isbn="9781234567890", source_file="b.epub")


def _sample_offsets() -> list[ChapterOffset]:
    first = ChapterOffset(byte=0, line=1)
    second = ChapterOffset(byte=_TEST_BYTE_OFFSET, line=5)
    return [first, second]


def _build_sample() -> tuple[str, list[ChapterRange], list[ChapterOffset]]:
    titles = ["One", "Two"]
    offsets = _sample_offsets()
    body = "## One\n\naaa\n\n## Two\n\nbbb\n"
    front_matter, ranges = build(_meta(), titles, offsets, body)
    return front_matter, ranges, offsets


def test_pad_number_constant_width() -> None:
    assert len(pad_number(5, "c")) == NUMERIC_WIDTH
    assert len(pad_number(_TEST_LARGE_NUMBER, "c")) == NUMERIC_WIDTH
    assert pad_number(7, "c").strip() == "7"


def test_pad_number_overflow_raises() -> None:
    with pytest.raises(OffsetOverflowError):
        pad_number(10**NUMERIC_WIDTH, "Chapter X")


def test_yaml_inline_quoting() -> None:
    assert yaml_inline_string("plain") == "plain"
    assert yaml_inline_string("has: colon").startswith('"')
    assert yaml_inline_string("# hash").startswith('"')
    assert yaml_inline_string(" pad ").startswith('"')


def test_build_size_invariant_between_passes() -> None:
    # build() returns the front matter only (not concatenated with the body).
    front_matter, ranges, offsets = _build_sample()
    expected_start_line = offsets[0].line + front_matter.count("\n")
    assert ranges[0].start_line == expected_start_line
    assert front_matter.startswith("---\n")
    assert ranges[0].end_line == ranges[1].start_line - 1


def test_render_includes_isbn_quoted() -> None:
    text = render(
        _meta(),
        [ChapterRange("C", start_line=1, end_line=2, start_byte=0, end_byte=5)],
    )
    assert 'isbn: "9781234567890"' in text
    assert text.endswith("---\n")


def test_chapters_without_pages_have_no_page_keys() -> None:
    front_matter, ranges = build(_meta(), ["A", "B"], _sample_offsets(), "x\n" * 10)

    assert "start_page" not in front_matter
    assert "end_page" not in front_matter
    assert [(chapter.start_page, chapter.end_page) for chapter in ranges] == [
        (None, None),
        (None, None),
    ]


def test_chapters_with_pages_render_page_keys() -> None:
    offsets = [ChapterOffset(byte=0, line=1, pages=(3, 7))]

    front_matter, ranges = build(_meta(), ["A"], offsets, "x\n")

    assert "    start_page: 3\n    end_page: 7\n" in front_matter
    assert (ranges[0].start_page, ranges[0].end_page) == (3, 7)
