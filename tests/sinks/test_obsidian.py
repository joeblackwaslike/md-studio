import os
import re
from collections.abc import Iterator, Mapping
from dataclasses import replace
from pathlib import Path, PurePath, PureWindowsPath

import pytest
import yaml

from md_studio.core.convert import RenderedMarkdown, convert
from md_studio.core.document import Document, DocumentMetadata
from md_studio.readers.epub import read_epub
from md_studio.sinks import SinkError
from md_studio.sinks.obsidian import ObsidianSink, is_relative_folder
from tests.readers._epub import ChapterSpec, build_epub

_FOLDER = "Book Notes"
_BACKSLASH = "\N{REVERSE SOLIDUS}"


def _document(tmp_path: Path) -> Document:
    specs = [
        ChapterSpec("Un", "<h1>Un</h1><p>Café été.</p>"),
        ChapterSpec("Deux", "<h1>Deux</h1><p>Hello.</p>"),
    ]
    return read_epub(build_epub(tmp_path / "book.epub", "Sample", specs))


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


def _rendered(text: str = "---\ntitle: T\n---\n## One\n") -> RenderedMarkdown:
    return RenderedMarkdown(text=text, front_matter="", body="", chapters=())


def _written_note(tmp_path: Path) -> tuple[Path, str]:
    document = _document(tmp_path)
    sink = ObsidianSink(_vault(tmp_path), folder=_FOLDER)
    extra = sink.properties(document.metadata, source="book.epub")
    written = sink.write(convert(document, extra=extra), name="Sample")
    return written, written.read_text(encoding="utf-8")


def _front_matter(text: str) -> Mapping[str, object]:
    return yaml.safe_load(text.split("---\n")[1])


def test_note_written_with_properties(tmp_path: Path) -> None:
    written, text = _written_note(tmp_path)
    properties = _front_matter(text)

    assert written == tmp_path / "vault" / _FOLDER / "Sample.md"
    assert (properties["title"], properties["source"]) == ("Sample", "book.epub")
    assert (properties["type"], properties["status"]) == ("book-note", "draft")
    assert properties["tags"] == ["book-notes"]


def test_created_is_iso_date_string(tmp_path: Path) -> None:
    _, text = _written_note(tmp_path)
    created = _front_matter(text)["created"]

    assert isinstance(created, str)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", created)


def test_note_chapter_offsets_point_at_headings(tmp_path: Path) -> None:
    _, text = _written_note(tmp_path)
    chapters = _front_matter(text)["chapters"]
    encoded = text.encode()

    assert len(chapters) == 2
    assert all(encoded[chapter["start_byte"] :].startswith(b"## ") for chapter in chapters)


def test_authors_mirrored_as_author_list(tmp_path: Path) -> None:
    document = _document(tmp_path)
    sink = ObsidianSink(_vault(tmp_path), folder=_FOLDER)

    extra = sink.properties(document.metadata, source="b.epub")

    assert extra["author"] == list(document.metadata.authors)


def test_missing_vault_raises_before_writing(tmp_path: Path) -> None:
    sink = ObsidianSink(tmp_path / "vault", folder=_FOLDER)

    with pytest.raises(SinkError):
        sink.write(_rendered(), name="n")

    assert not (tmp_path / "vault").exists()


def test_vault_that_is_a_file_raises(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.write_text("x")

    with pytest.raises(SinkError):
        ObsidianSink(vault, folder=_FOLDER).write(_rendered(), name="n")


@pytest.fixture
def readonly_vault(tmp_path: Path) -> Iterator[Path]:
    vault = _vault(tmp_path)
    vault.chmod(0o500)
    yield vault
    vault.chmod(0o700)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_unwritable_vault_raises_before_writing(readonly_vault: Path) -> None:
    with pytest.raises(SinkError):
        ObsidianSink(readonly_vault, folder=_FOLDER).write(_rendered(), name="n")

    assert not (readonly_vault / _FOLDER).exists()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ('a/b\N{REVERSE SOLIDUS}c:d*e?f"g<h>i|j', "a b c d e f g h i j.md"),
        ("..hidden  title ", "hidden title.md"),
        ("C# Book", "C Book.md"),
        ("a#[x]^", "a x.md"),
        ("\u200b\u200b", "untitled.md"),
        ("a\u202eb", "a b.md"),
        ("x\x7fy", "x y.md"),
        ("x\x85y", "x y.md"),
        ("x\ue000y", "x y.md"),
        (". . x", "x.md"),
        ("a. . ", "a.md"),
        ("a\x00b", "a b.md"),
        ("..", "untitled.md"),
        (".", "untitled.md"),
        ('/\N{REVERSE SOLIDUS}:*?"<>|', "untitled.md"),
        ("a \t\n  b", "a b.md"),
        ("///", "untitled.md"),
        ("", "untitled.md"),
    ],
)
def test_filename_sanitized(tmp_path: Path, name: str, expected: str) -> None:
    sink = ObsidianSink(_vault(tmp_path), folder=_FOLDER)

    written = sink.write(_rendered(), name=name)

    assert written == tmp_path / "vault" / _FOLDER / expected


def test_existing_note_not_overwritten(tmp_path: Path) -> None:
    sink = ObsidianSink(_vault(tmp_path), folder=_FOLDER)
    first = sink.write(_rendered("one"), name="n")

    with pytest.raises(FileExistsError):
        sink.write(_rendered("two"), name="n")

    assert first.read_text(encoding="utf-8") == "one"


@pytest.mark.parametrize("name", ["é" * 150, "日" * 100, "a" * 300])
def test_long_names_fit_filename_byte_limit(tmp_path: Path, name: str) -> None:
    sink = ObsidianSink(_vault(tmp_path), folder=_FOLDER)

    written = sink.write(_rendered(), name=name)

    assert len(written.name.encode("utf-8")) <= 240
    assert written.name.endswith(".md")
    assert written.read_text(encoding="utf-8") == _rendered().text


@pytest.mark.parametrize("folder", ["", ".", "/abs", "../up", "a/../b"])
def test_unsafe_folder_rejected(tmp_path: Path, folder: str) -> None:
    with pytest.raises(SinkError):
        ObsidianSink(_vault(tmp_path), folder=folder)


def test_nested_relative_folder_allowed(tmp_path: Path) -> None:
    sink = ObsidianSink(_vault(tmp_path), folder="Books/Tech")

    written = sink.write(_rendered(), name="n")

    assert written == tmp_path / "vault" / "Books" / "Tech" / "n.md"


def test_names_that_sanitize_alike_do_not_overwrite(tmp_path: Path) -> None:
    sink = ObsidianSink(_vault(tmp_path), folder=_FOLDER)
    first = sink.write(_rendered("one"), name="a:b")

    with pytest.raises(FileExistsError):
        sink.write(_rendered("two"), name="a*b")

    assert first.read_text(encoding="utf-8") == "one"


def test_properties_without_authors_has_no_author_key(tmp_path: Path) -> None:
    sink = ObsidianSink(_vault(tmp_path), folder=_FOLDER)

    assert "author" not in sink.properties(DocumentMetadata(title="T"), source="b.epub")


def _non_ascii_note(tmp_path: Path) -> bytes:
    specs = [ChapterSpec("Café", "<h1>Café</h1><p>été</p>"), ChapterSpec("Deux", "<h1>Deux</h1>")]
    source = read_epub(build_epub(tmp_path / "b.epub", "Zoë 日本", specs))
    document = replace(source, metadata=replace(source.metadata, authors=("Zoë 日本",)))
    sink = ObsidianSink(_vault(tmp_path), folder=_FOLDER)
    extra = sink.properties(document.metadata, source="b.epub")
    return sink.write(convert(document, extra=extra), name="n").read_bytes()


def test_offsets_hold_for_non_ascii_author_and_title(tmp_path: Path) -> None:
    raw = _non_ascii_note(tmp_path)
    chapters = _front_matter(raw.decode("utf-8"))["chapters"]

    assert all(raw[chapter["start_byte"] :].startswith(b"## ") for chapter in chapters)
    assert chapters[-1]["end_byte"] == len(raw) - 1


def test_vault_check_reports_folder_that_is_a_file(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    (vault / _FOLDER).write_text("x")
    sink = ObsidianSink(vault, folder=_FOLDER)

    with pytest.raises(SinkError, match="not a directory"):
        sink.check()
    with pytest.raises(SinkError, match="not a directory"):
        sink.write(_rendered(), name="n")


def test_vault_check_passes_for_writable_vault(tmp_path: Path) -> None:
    ObsidianSink(_vault(tmp_path), folder=_FOLDER).check()


@pytest.mark.parametrize(
    "folder",
    [
        PureWindowsPath(f"{_BACKSLASH}outside"),
        PureWindowsPath("D:Notes"),
        PureWindowsPath(f"C:{_BACKSLASH}x"),
        PurePath("/abs"),
    ],
)
def test_anchored_folders_are_not_relative(folder: PurePath) -> None:
    assert not is_relative_folder(folder)


@pytest.mark.parametrize(
    "folder", [PurePath("Book Notes"), PurePath("a/b"), PureWindowsPath(f"a{_BACKSLASH}b")]
)
def test_plain_relative_folders_are_relative(folder: PurePath) -> None:
    assert is_relative_folder(folder)


@pytest.fixture
def readonly_notes_folder(tmp_path: Path) -> Iterator[Path]:
    folder = _vault(tmp_path) / _FOLDER
    folder.mkdir()
    folder.chmod(0o500)
    yield folder
    folder.chmod(0o700)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_check_rejects_unwritable_existing_notes_folder(readonly_notes_folder: Path) -> None:
    sink = ObsidianSink(readonly_notes_folder.parent, folder=_FOLDER)

    with pytest.raises(SinkError, match="Notes folder is not writable"):
        sink.check()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_check_rejects_unwritable_existing_parent_of_missing_folder(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    parent = vault / "Books"
    parent.mkdir()
    parent.chmod(0o500)
    try:
        with pytest.raises(SinkError, match="Notes folder is not writable"):
            ObsidianSink(vault, folder="Books/Tech").check()
    finally:
        parent.chmod(0o700)


def test_check_allows_missing_notes_folder_in_writable_vault(tmp_path: Path) -> None:
    ObsidianSink(_vault(tmp_path), folder=_FOLDER).check()

    assert not (tmp_path / "vault" / _FOLDER).exists()
