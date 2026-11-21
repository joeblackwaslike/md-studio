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
    compression: int = zipfile.ZIP_DEFLATED,
) -> Path:
    """Rewrite *epub* in place without the *drop* members and with *replace* contents."""
    swaps = replace or {}
    members = {**_read_members(epub), **swaps}
    with zipfile.ZipFile(epub, "w", compression) as target:
        for name, payload in members.items():
            if name not in drop:
                target.writestr(name, payload)
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


_SPACED = "OEBPS/ch 0.xhtml"


def _percent_encode_chapter_href(epub: Path) -> Path:
    """Rename the first chapter to ``ch 0.xhtml`` and reference it as ``ch%200.xhtml``."""
    members = _read_members(epub)
    opf = members[_OPF].decode("utf-8").replace('href="ch0.xhtml"', 'href="ch%200.xhtml"')
    ncx = members["OEBPS/toc.ncx"].decode("utf-8").replace('src="ch0.xhtml"', 'src="ch%200.xhtml"')
    return _rewrite_zip(
        epub,
        drop=("OEBPS/ch0.xhtml",),
        replace={
            _OPF: opf.encode("utf-8"),
            "OEBPS/toc.ncx": ncx.encode("utf-8"),
            _SPACED: members["OEBPS/ch0.xhtml"],
        },
    )


def test_percent_encoded_manifest_href_reads_chapter_content(tmp_path: Path) -> None:
    specs = [ChapterSpec("Nav Title", "<p>hello spaced world</p>")]
    epub = _percent_encode_chapter_href(build_epub(tmp_path / "sp.epub", "T", specs))

    chapter = read_epub(epub).chapters[0]

    assert "hello spaced world" in chapter.element.text_content()


def test_percent_encoded_ncx_href_still_supplies_the_title(tmp_path: Path) -> None:
    specs = [ChapterSpec("Nav Title", "<p>no heading here</p>")]
    epub = _percent_encode_chapter_href(build_epub(tmp_path / "sp.epub", "T", specs))

    assert read_epub(epub).chapters[0].title == "Nav Title"


_DOCTYPE = '<!DOCTYPE package [<!ENTITY xxe SYSTEM "{uri}">]>'


def _hostile_opf(epub: Path, uri: str) -> bytes:
    """Return the OPF with an external-entity DOCTYPE and the title set to that entity."""
    opf = _read_members(epub)[_OPF].decode("utf-8")
    declaration, _, rest = opf.partition("?>\n")
    hostile = f"{declaration}?>\n{_DOCTYPE.format(uri=uri)}\n{rest}"
    return hostile.replace("<dc:title>T</dc:title>", "<dc:title>&xxe;</dc:title>").encode("utf-8")


def test_external_entities_in_the_opf_are_not_resolved(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-VALUE", encoding="utf-8")
    epub = build_epub(tmp_path / "x.epub", "T", [ChapterSpec("One", "<p>x</p>")])
    hostile = _hostile_opf(epub, secret.as_uri())

    document = read_epub(_rewrite_zip(epub, replace={_OPF: hostile}))

    assert "TOP-SECRET-VALUE" not in document.metadata.title


def test_streamed_length_is_capped_even_when_the_declared_size_is_small(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    epub = build_epub(tmp_path / "s.epub", "T", [ChapterSpec("One", "<p>x</p>" * 1000)])
    monkeypatch.setattr("md_studio.readers.epub.archive._declared_size", lambda archive, path: 0)
    monkeypatch.setattr("md_studio.readers.epub.archive.MAX_MEMBER_BYTES", 3000)

    with pytest.raises(ReadError, match=r"OEBPS/ch0\.xhtml exceeds"):
        read_epub(epub)


def test_corrupt_lzma_member_raises_member_read_error(tmp_path: Path) -> None:
    epub = build_epub(tmp_path / "z.epub", "T", [ChapterSpec("One", "<p>hello</p>" * 50)])
    _rewrite_zip(epub, compression=zipfile.ZIP_LZMA)
    blob = bytearray(epub.read_bytes())
    payload = blob.find(b"OEBPS/ch0.xhtml") + len(b"OEBPS/ch0.xhtml")
    for offset in range(payload + 12, payload + 24):
        blob[offset] ^= 0xFF
    epub.write_bytes(bytes(blob))

    with pytest.raises(ReadError, match="Cannot read archive member"):
        read_epub(epub)


def test_invalid_utf8_member_name_raises_read_error(tmp_path: Path) -> None:
    epub = build_epub(tmp_path / "u.epub", "T", [ChapterSpec("One", "<p>x</p>")])
    blob = bytearray(epub.read_bytes())
    entry = re.search(rb"PK\x01\x02.{42}mimetype", bytes(blob), re.DOTALL)
    assert entry is not None
    flags = struct.unpack_from("<H", blob, entry.start() + 8)[0]
    struct.pack_into("<H", blob, entry.start() + 8, flags | 0x800)
    blob[entry.start() + 46] = 0xFF
    epub.write_bytes(bytes(blob))

    with pytest.raises(ReadError, match="Not a valid EPUB"):
        read_epub(epub)
