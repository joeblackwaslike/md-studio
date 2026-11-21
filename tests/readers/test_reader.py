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


def _read_members(epub: Path) -> dict[str, bytes]:
    """Return every member of *epub* by name."""
    with zipfile.ZipFile(epub) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _rewrite_zip(
    epub: Path,
    *,
    drop: tuple[str, ...] = (),
    replace: dict[str, bytes] | None = None,
) -> Path:
    """Rewrite *epub* in place without the *drop* members and with *replace* contents."""
    swaps = replace or {}
    members = _read_members(epub)
    with zipfile.ZipFile(epub, "w", zipfile.ZIP_DEFLATED) as target:
        for name, payload in members.items():
            if name not in drop:
                target.writestr(name, swaps.get(name, payload))
    return epub


def _without_ncx(tmp_path: Path, specs: list[ChapterSpec]) -> Document:
    epub = build_epub(tmp_path / "n.epub", "T", specs)
    return read_epub(_rewrite_zip(epub, drop=("OEBPS/toc.ncx",)))


def test_ncx_label_wins_over_heading(tmp_path: Path) -> None:
    specs = [ChapterSpec("Nav Label", "<h1>Real Heading</h1><p>body</p>")]

    document = read_epub(build_epub(tmp_path / "h.epub", "T", specs))

    assert document.chapters[0].title == "Nav Label"


def test_falls_back_to_heading_title(tmp_path: Path) -> None:
    specs = [ChapterSpec("Ignored", "<h1>Real Heading</h1><p>body</p>")]

    assert _without_ncx(tmp_path, specs).chapters[0].title == "Real Heading"


def test_falls_back_to_file_stem_without_heading(tmp_path: Path) -> None:
    specs = [ChapterSpec("Ignored", "<p>no heading here</p>")]

    assert _without_ncx(tmp_path, specs).chapters[0].title == "ch0"


_OPF = "OEBPS/content.opf"
_CH1 = "OEBPS/ch1.xhtml"


@pytest.mark.parametrize(
    ("drop", "replace", "message"),
    [
        ((_OPF,), None, "OPF not found in archive"),
        ((_CH1,), None, "Spine references missing file"),
        ((), {_OPF: b"<package"}, "Malformed XML"),
    ],
    ids=["missing-opf", "missing-spine-file", "malformed-opf"],
)
def test_structurally_broken_epub_raises(
    tmp_path: Path,
    drop: tuple[str, ...],
    replace: dict[str, bytes] | None,
    message: str,
) -> None:
    specs = [ChapterSpec("Zero", "<p>0</p>"), ChapterSpec("One", "<p>1</p>")]
    epub = _rewrite_zip(build_epub(tmp_path / "b.epub", "T", specs), drop=drop, replace=replace)

    with pytest.raises(ReadError, match=message):
        read_epub(epub)


_ART_ITEM = 'id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"'
_SVG_ITEM = 'id="ch1" href="ch1.xhtml" media-type="image/svg+xml"'


def _mark_second_chapter_as_svg(epub: Path) -> Path:
    opf = _read_members(epub)[_OPF].decode("utf-8")
    swapped = opf.replace(_ART_ITEM, _SVG_ITEM)
    assert swapped != opf
    return _rewrite_zip(epub, replace={_OPF: swapped.encode("utf-8")})


def test_non_xhtml_spine_items_are_skipped(tmp_path: Path) -> None:
    specs = [ChapterSpec(title, f"<p>{title}</p>") for title in ("Cover", "Art", "Two")]
    epub = _mark_second_chapter_as_svg(build_epub(tmp_path / "s.epub", "T", specs))

    assert [chapter.title for chapter in read_epub(epub).chapters] == ["Cover", "Two"]


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


def test_unrelated_runtime_error_from_parsing_is_not_relabelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    epub = build_epub(tmp_path / "p.epub", "T", [ChapterSpec("One", "<p>x</p>")])
    monkeypatch.setattr("md_studio.readers.epub.document.parse_xml", _explode)

    with pytest.raises(RuntimeError, match="parser bug"):
        read_epub(epub)


def _explode(raw: bytes, *, source: str) -> None:
    raise RuntimeError("parser bug")


def test_oversize_chapter_member_raises_read_error_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    big = ChapterSpec("One", "<p>x</p>" * 1000)
    epub = build_epub(tmp_path / "big.epub", "T", [big])
    monkeypatch.setattr("md_studio.readers.epub.archive.MAX_MEMBER_BYTES", 3000)

    with pytest.raises(ReadError, match=r"OEBPS/ch0\.xhtml exceeds"):
        read_epub(epub)
