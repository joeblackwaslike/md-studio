"""Tests for caller-supplied front-matter extra properties."""

import pytest
import yaml

from md_studio.core import ir
from md_studio.core.exceptions import MdStudioError
from md_studio.core.frontmatter import build
from md_studio.core.render import ChapterOffset

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


@pytest.mark.parametrize("key", ["title", "chapters", "source_file"])
def test_extra_key_collision_raises(key: str) -> None:
    with pytest.raises(MdStudioError, match=key):
        build(_meta(), list(_TITLES), _offsets(), _BODY, extra={key: "x"})


@pytest.mark.parametrize("key", ["", "1abc", "has space", "a:b", "x\ny"])
def test_invalid_extra_key_raises(key: str) -> None:
    with pytest.raises(MdStudioError, match="invalid"):
        build(_meta(), list(_TITLES), _offsets(), _BODY, extra={key: "x"})


@pytest.mark.parametrize("extra", [None, {}])
def test_no_extra_leaves_output_unchanged(extra: dict[str, str | list[str]] | None) -> None:
    baseline = build(_meta(), list(_TITLES), _offsets(), _BODY)

    assert build(_meta(), list(_TITLES), _offsets(), _BODY, extra=extra) == baseline
    assert "tags" not in baseline[0]
