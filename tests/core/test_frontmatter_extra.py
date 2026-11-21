"""Tests for caller-supplied front-matter extra properties."""

from pathlib import Path

import pytest
import yaml

from md_studio.core import ir
from md_studio.core.convert import convert
from md_studio.core.exceptions import MdStudioError
from md_studio.core.frontmatter import build
from md_studio.core.frontmatter.document import _RESERVED_KEYS
from md_studio.core.render import ChapterOffset
from md_studio.readers.epub import read_epub
from tests.readers._epub import ChapterSpec, build_epub

_BODY = "## One\n\naaa\n\n## Tëst Two\n\nbbb\n"
_SECOND_BYTE = len(b"## One\n\naaa\n\n")
_TITLES = ("One", "Tëst Two")
_BACKSLASH = chr(92)
_NEWLINE_VALUE = f'line1\nsay "hi" {_BACKSLASH} end'
_ODD_VALUE = "\t\x07é"


def _meta() -> ir.BookMeta:
    return ir.BookMeta(title="Book", authors=("A",), isbn="9781234567890", source_file="b.epub")


def _offsets() -> list[ChapterOffset]:
    return [ChapterOffset(byte=0, line=1), ChapterOffset(byte=_SECOND_BYTE, line=5)]


def _extra() -> dict[str, str | list[str]]:
    return {"source": "arxiv", "tags": ["math", "papers", "to-read"]}


def _parse(front_matter: str) -> dict[str, object]:
    return yaml.safe_load(front_matter.split("---\n")[1])


def test_extra_properties_appear_before_chapters() -> None:
    front_matter, _ = build(_meta(), list(_TITLES), _offsets(), _BODY, extra=_extra())

    assert front_matter.index("source_file:") < front_matter.index("source:")
    assert front_matter.index("source:") < front_matter.index("chapters:")
    assert front_matter.index("tags:") < front_matter.index("chapters:")


def test_offsets_remain_valid_with_extra() -> None:
    front_matter, ranges = build(_meta(), list(_TITLES), _offsets(), _BODY, extra=_extra())
    text = (front_matter + _BODY).encode()

    assert len(ranges) == len(_TITLES)
    for chapter in ranges:
        assert text[chapter.start_byte : chapter.end_byte].startswith(b"##")


def test_front_matter_parses_with_yaml() -> None:
    front_matter, _ = build(_meta(), list(_TITLES), _offsets(), _BODY, extra=_extra())
    parsed = _parse(front_matter)

    assert parsed["source"] == "arxiv"
    assert parsed["tags"] == ["math", "papers", "to-read"]
    chapters = parsed["chapters"]
    assert isinstance(chapters, list)
    assert all(isinstance(entry, dict) for entry in chapters)
    assert all(isinstance(entry["start_byte"], int) for entry in chapters)


def test_extra_value_with_newline_and_quotes_round_trips() -> None:
    extra: dict[str, str | list[str]] = {
        "note": _NEWLINE_VALUE,
        "items": [_NEWLINE_VALUE, "true", _ODD_VALUE],
    }
    front_matter, _ = build(_meta(), list(_TITLES), _offsets(), _BODY, extra=extra)
    parsed = _parse(front_matter)

    assert parsed["note"] == _NEWLINE_VALUE
    assert parsed["items"] == [_NEWLINE_VALUE, "true", _ODD_VALUE]


@pytest.mark.parametrize("key", _RESERVED_KEYS)
def test_extra_key_collision_raises(key: str) -> None:
    with pytest.raises(MdStudioError, match=key):
        build(_meta(), list(_TITLES), _offsets(), _BODY, extra={key: "x"})


@pytest.mark.parametrize("key", ["Title", "CHAPTERS", "Source_File"])
def test_extra_key_collision_is_case_insensitive(key: str) -> None:
    with pytest.raises(MdStudioError, match=key):
        build(_meta(), list(_TITLES), _offsets(), _BODY, extra={key: "x"})


def test_isbn_with_quote_and_newline_cannot_break_document() -> None:
    hostile = 'x"\ninjected: yes'
    meta = ir.BookMeta(title="Book", isbn=hostile)

    front_matter, _ = build(meta, list(_TITLES), _offsets(), _BODY)
    parsed = _parse(front_matter)

    assert parsed["isbn"] == hostile
    assert "injected" not in parsed


@pytest.mark.parametrize("key", ["", "1abc", "has space", "a:b", "x\ny"])
def test_invalid_extra_key_raises(key: str) -> None:
    with pytest.raises(MdStudioError, match="invalid"):
        build(_meta(), list(_TITLES), _offsets(), _BODY, extra={key: "x"})


_EXPECTED_DEFAULT = """---
title: Book
authors: [A]
isbn: "9781234567890"
source_file: b.epub
chapters:
  - title: One
    start_line:         18
    end_line:         21
    start_byte:        329
    end_byte:        341
  - title: Tëst Two
    start_line:         22
    end_line:         24
    start_byte:        342
    end_byte:        359
---
"""
_SPECS = (ChapterSpec("Intro", "<p>ça va</p>"), ChapterSpec("Café ☕", "<p>naïve</p>"))
_MULTIBYTE = "Café ☕ 日本語"
_ESCAPE_CASES = (
    "\x7f",
    "\x85",
    "\u2028",
    "\u2029",
    "\x00",
    "\x1f",
    "\U0001f600",
    f'{_BACKSLASH}"',
    f'"{_BACKSLASH}',
)


@pytest.mark.parametrize("extra", [None, {}])
def test_no_extra_leaves_output_unchanged(extra: dict[str, str | list[str]] | None) -> None:
    front_matter, _ = build(_meta(), list(_TITLES), _offsets(), _BODY, extra=extra)

    assert front_matter == _EXPECTED_DEFAULT


def test_empty_list_and_empty_string_round_trip() -> None:
    extra: dict[str, str | list[str]] = {"tags": [], "note": ""}
    front_matter, _ = build(_meta(), list(_TITLES), _offsets(), _BODY, extra=extra)
    parsed = _parse(front_matter)

    assert parsed["tags"] == []
    assert parsed["note"] == ""


def test_multibyte_extra_keeps_offsets_and_lines_valid(tmp_path: Path) -> None:
    extra: dict[str, str | list[str]] = {"note": _MULTIBYTE, "tags": [_MULTIBYTE, "日本", "x"]}
    rendered = convert(
        read_epub(build_epub(tmp_path / "m.epub", "Unicode", list(_SPECS))), extra=extra
    )
    raw = rendered.text.encode("utf-8")
    lines = rendered.text.split("\n")

    assert len(rendered.chapters) == len(_SPECS)
    for entry in rendered.chapters:
        assert raw[entry.start_byte : entry.end_byte + 1].startswith(f"## {entry.title}".encode())
        assert lines[entry.start_line - 1].startswith(f"## {entry.title}")
    assert rendered.chapters[-1].end_byte == len(raw) - 1


@pytest.mark.parametrize(
    "key",
    ["on", "off", "yes", "no", "y", "n", "true", "false", "null", "Yes", "NULL", "True"],
)
def test_yaml_non_string_extra_key_raises(key: str) -> None:
    with pytest.raises(MdStudioError, match="boolean or null"):
        build(_meta(), list(_TITLES), _offsets(), _BODY, extra={key: "x"})


def test_reserved_keys_cover_every_header_key() -> None:
    meta = ir.BookMeta(
        title="T",
        authors=("A",),
        publisher="P",
        published="2024-01-02",
        isbn="9781234567890",
        language="en",
        source_file="b.epub",
    )
    front_matter, _ = build(meta, list(_TITLES), _offsets(), _BODY)
    emitted = set(_parse(front_matter))

    assert emitted <= set(_RESERVED_KEYS)
    assert set(_RESERVED_KEYS) - emitted == set()


@pytest.mark.parametrize("raw", _ESCAPE_CASES)
def test_escaper_round_trips_special_characters(raw: str) -> None:
    extra: dict[str, str | list[str]] = {"note": raw, "items": [raw]}
    front_matter, _ = build(_meta(), list(_TITLES), _offsets(), _BODY, extra=extra)
    parsed = _parse(front_matter)

    assert parsed["note"] == raw
    assert parsed["items"] == [raw]
