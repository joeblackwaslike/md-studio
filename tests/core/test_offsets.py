"""Offset-correctness tests: front-matter line/byte ranges must seek correctly.

Ported from the books-for-bots ``tests/offsets.rs``: verify that each recorded byte
and line offset lands on the chapter's ``## {title}`` heading, that ranges tile the
file, and (once) that the YAML front matter carries the same numbers.
"""

from itertools import pairwise
from pathlib import Path
from types import MappingProxyType

import pytest

from md_studio.core.convert import RenderedMarkdown, convert
from md_studio.core.frontmatter import ChapterRange
from md_studio.readers.epub import read_epub
from tests.readers._epub import ChapterSpec, build_epub

_TITLES = ("Alpha Chapter", "Beta Chapter", "Gamma Chapter")

_BODIES = MappingProxyType({
    "empty": "",
    "trailing-pre-with-blank-lines": "<p>text</p><pre>line one\n\n\nline four\n\n</pre>",
    "list": "<ul><li>one</li><li>two<ul><li>nested</li></ul></li></ul>",
    "table": "<table><tr><th>h</th></tr><tr><td>c</td></tr></table>",
    "redundant-h1": "<h1>{title}</h1><p>after heading</p>",
    "footnote": (
        '<div xmlns:epub="http://www.idpf.org/2007/ops">'
        '<p>text<sup><a href="#fn1" epub:type="noteref">1</a></sup></p>'
        '<aside id="fn1" epub:type="footnote"><p>note</p></aside></div>'
    ),
})


def _build(tmp_path: Path, bodies: tuple[str, str, str]) -> Path:
    specs = [
        ChapterSpec(title, body.format(title=title))
        for title, body in zip(_TITLES, bodies, strict=True)
    ]
    return build_epub(tmp_path / "off.epub", "Off", specs)


def _convert(tmp_path: Path, *, extensions: list[str] | None = None) -> RenderedMarkdown:
    middle = f"<p>{'bbb ' * 60}</p>{'<p>more</p>' * 5}"
    bodies = ("<p>aaa</p>", middle, "<p>ccc</p>")
    return convert(read_epub(_build(tmp_path, bodies)), extensions=extensions)


def _assert_covers_one_chapter(raw: bytes, chapters: tuple[ChapterRange, ...], index: int) -> None:
    entry = chapters[index]
    segment = raw[entry.start_byte : entry.end_byte + 1].decode("utf-8")
    later = [f"## {other.title}" for other in chapters[index + 1 :]]
    assert segment.startswith(f"## {entry.title}")
    assert not any(heading in segment for heading in later)


@pytest.mark.parametrize("body", list(_BODIES.values()), ids=list(_BODIES))
def test_byte_ranges_cover_exactly_one_chapter(tmp_path: Path, body: str) -> None:
    rendered = convert(read_epub(_build(tmp_path, ("<p>first</p>", body, body))))
    raw = rendered.text.encode("utf-8")

    for index, _entry in enumerate(rendered.chapters):
        _assert_covers_one_chapter(raw, rendered.chapters, index)
    assert rendered.chapters[-1].end_byte == len(raw) - 1


def test_line_offsets_seek_to_heading(tmp_path: Path) -> None:
    rendered = _convert(tmp_path)
    lines = rendered.text.split("\n")

    for entry in rendered.chapters:
        assert lines[entry.start_line - 1].startswith(f"## {entry.title}")


def test_ranges_tile_the_file(tmp_path: Path) -> None:
    rendered = _convert(tmp_path)

    for earlier, later in pairwise(rendered.chapters):
        assert earlier.end_line == later.start_line - 1
        assert earlier.end_byte == later.start_byte - 1
    assert rendered.chapters[-1].end_line == rendered.text.count("\n")


def test_offsets_survive_extensions(tmp_path: Path) -> None:
    rendered = _convert(tmp_path, extensions=["fix-headings", "remove-footnotes"])
    raw = rendered.text.encode("utf-8")

    for entry in rendered.chapters:
        assert raw[entry.start_byte :].decode("utf-8").startswith(f"## {entry.title}")


def _yaml_chapter_block(front_matter: str) -> list[str]:
    """Return the lines under the front matter's ``chapters:`` key."""
    lines = front_matter.split("\n")
    start = lines.index("chapters:") + 1
    return lines[start : lines.index("---", 1)]


def _yaml_numbers(entry_lines: list[str]) -> list[int]:
    """Parse the four numeric fields that follow a ``- title:`` line."""
    return [int(line.partition(":")[2]) for line in entry_lines[1:5]]


def test_front_matter_yaml_lists_the_chapter_ranges(tmp_path: Path) -> None:
    rendered = _convert(tmp_path)
    block = _yaml_chapter_block(rendered.front_matter)
    entries = [block[start : start + 5] for start in range(0, len(block), 5)]

    expected = [
        (
            f"- title: {entry.title}",
            [entry.start_line, entry.end_line, entry.start_byte, entry.end_byte],
        )
        for entry in rendered.chapters
    ]
    assert [(lines[0].strip(), _yaml_numbers(lines)) for lines in entries] == expected
