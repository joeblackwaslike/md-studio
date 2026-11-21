"""Chapter ranges are UTF-8 byte offsets, not character offsets."""

from pathlib import Path

from md_studio.core.convert import convert
from md_studio.readers.epub import read_epub
from tests.readers._epub import ChapterSpec, build_epub

TITLE = "Café ☕"


def test_offsets_count_utf8_bytes(tmp_path: Path) -> None:
    specs = [
        ChapterSpec("Intro", "<p>ça va</p>"),
        ChapterSpec(TITLE, "<p>naïve ☕ text</p>"),
    ]
    rendered = convert(read_epub(build_epub(tmp_path / "u.epub", "Unicode", specs)))
    chapter = next(entry for entry in rendered.chapters if entry.title == TITLE)
    raw = rendered.text.encode("utf-8")
    assert raw[chapter.start_byte : chapter.end_byte].startswith(f"## {TITLE}".encode())
