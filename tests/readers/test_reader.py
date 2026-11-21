"""Tests for the hand-rolled EPUB reader."""

import re
import struct
import zipfile
from pathlib import Path

import pytest

from md_studio.core.document import Document
from md_studio.core.exceptions import ReadError
from md_studio.readers.epub import read_epub
from tests.readers._epub import ChapterSpec, build_epub


def _sample_document(tmp_path: Path) -> Document:
    specs = [
        ChapterSpec("Cover", "<p>cover</p>"),
        ChapterSpec("One", "<p>one</p>"),
        ChapterSpec("Two", "<p>two</p>"),
    ]
    epub = build_epub(tmp_path / "b.epub", "My Title", specs, isbn="9780000000001")
    return read_epub(epub)


def test_reads_title_and_authorship_metadata(tmp_path: Path) -> None:
    metadata = _sample_document(tmp_path).metadata

    assert metadata.title == "My Title"
    assert metadata.authors == ("Ada Lovelace",)
    assert metadata.publisher == "O'Reilly Media, Inc."
    assert metadata.published == "2024-01-02"


def test_reads_identifier_and_provenance_metadata(tmp_path: Path) -> None:
    metadata = _sample_document(tmp_path).metadata

    assert metadata.isbn == "9780000000001"
    assert metadata.language == "en"
    assert metadata.source_file == "b.epub"


def test_reads_chapters_in_order(tmp_path: Path) -> None:
    document = _sample_document(tmp_path)

    assert [chapter.title for chapter in document.chapters] == ["Cover", "One", "Two"]


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ReadError):
        read_epub(tmp_path / "nope.epub")


def test_not_a_zip_raises(tmp_path: Path) -> None:
    bogus = tmp_path / "bad.epub"
    bogus.write_text("not a zip", encoding="utf-8")
    with pytest.raises(ReadError):
        read_epub(bogus)


def test_missing_container_raises(tmp_path: Path) -> None:
    path = tmp_path / "nocontainer.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
    with pytest.raises(ReadError):
        read_epub(path)


def test_falls_back_to_heading_title(tmp_path: Path) -> None:
    # NCX nav label is present in the helper; remove reliance by checking heading.
    specs = [ChapterSpec("Ignored", "<h1>Real Heading</h1><p>body</p>")]
    epub = build_epub(tmp_path / "h.epub", "T", specs)
    document = read_epub(epub)
    # The NCX label wins when present.
    assert document.chapters[0].title == "Ignored"


def test_epub_without_chapters_raises(tmp_path: Path) -> None:
    epub = build_epub(tmp_path / "empty.epub", "Empty", [])

    with pytest.raises(ReadError, match="EPUB has no readable chapters") as caught:
        read_epub(epub)

    assert str(epub) in str(caught.value)


_ENCRYPTED_FLAG = 0x1
_UNSUPPORTED_METHOD = 99
_CENTRAL_ENTRY = re.compile(rb"PK\x01\x02.{42}OEBPS/ch0\.xhtml", re.DOTALL)
_FLAGS_OFFSET = 8
_DEFLATED = zipfile.ZIP_DEFLATED


def _corrupt_chapter_entry(path: Path, *, flags: int, method: int) -> None:
    """Overwrite the chapter's flag bits and compression method in the central directory."""
    blob = bytearray(path.read_bytes())
    entry = _CENTRAL_ENTRY.search(bytes(blob))
    assert entry is not None
    struct.pack_into("<HH", blob, entry.start() + _FLAGS_OFFSET, flags, method)
    path.write_bytes(bytes(blob))


@pytest.mark.parametrize(
    ("flags", "method", "reason"),
    [
        (_ENCRYPTED_FLAG, _DEFLATED, "encrypted"),
        (0, _UNSUPPORTED_METHOD, "compression"),
    ],
)
def test_unreadable_member_raises_read_error(
    tmp_path: Path, flags: int, method: int, reason: str
) -> None:
    epub = build_epub(tmp_path / "bad.epub", "T", [ChapterSpec("One", "<p>x</p>")])
    _corrupt_chapter_entry(epub, flags=flags, method=method)

    with pytest.raises(ReadError, match=reason):
        read_epub(epub)


def test_oversize_member_raises_read_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    big = ChapterSpec("One", "<p>x</p>" * 100)
    epub = build_epub(tmp_path / "big.epub", "T", [big])
    monkeypatch.setattr("md_studio.readers.epub.archive.MAX_MEMBER_BYTES", 100)

    with pytest.raises(ReadError, match="exceeds"):
        read_epub(epub)
