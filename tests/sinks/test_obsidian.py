import re
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
import yaml

from md_studio.core.convert import RenderedMarkdown, convert
from md_studio.core.document import Document
from md_studio.readers.epub import read_epub
from md_studio.sinks import SinkError
from md_studio.sinks.obsidian import ObsidianSink
from tests.readers._epub import ChapterSpec, build_epub

_FOLDER = "Book Notes"


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


def test_unwritable_vault_raises_before_writing(readonly_vault: Path) -> None:
    with pytest.raises(SinkError):
        ObsidianSink(readonly_vault, folder=_FOLDER).write(_rendered(), name="n")

    assert not (readonly_vault / _FOLDER).exists()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ('a/b\N{REVERSE SOLIDUS}c:d*e?f"g<h>i|j', "a b c d e f g h i j.md"),
        ("..hidden  title ", "hidden title.md"),
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
