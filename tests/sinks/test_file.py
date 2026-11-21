from pathlib import Path

import pytest

from md_studio.core.convert import RenderedMarkdown
from md_studio.sinks.file import FileSink


def _rendered() -> RenderedMarkdown:
    return RenderedMarkdown(
        text="---\ntitle: T\n---\n## One\n\nBody é\n",
        front_matter="---\ntitle: T\n---\n",
        body="## One\n\nBody é\n",
        chapters=[],
    )


def test_file_sink_writes_front_matter_then_body(tmp_path: Path) -> None:
    dest = tmp_path / "nested" / "book.md"

    written = FileSink(dest).write(_rendered(), name="book")

    assert written == dest
    assert dest.read_bytes() == _rendered().text.encode("utf-8")
    assert dest.read_text(encoding="utf-8").startswith("---\ntitle: T\n---\n## One")


def test_file_sink_refuses_overwrite_without_force(tmp_path: Path) -> None:  # noqa: WPS118
    dest = tmp_path / "book.md"
    dest.write_text("old", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Refusing to overwrite existing file"):
        FileSink(dest).write(_rendered(), name="book")

    assert dest.read_text(encoding="utf-8") == "old"


def test_file_sink_overwrites_with_force(tmp_path: Path) -> None:
    dest = tmp_path / "book.md"
    dest.write_text("old", encoding="utf-8")

    FileSink(dest, force=True).write(_rendered(), name="book")

    assert dest.read_text(encoding="utf-8") == _rendered().text


def test_file_sink_rejects_directory_destination(tmp_path: Path) -> None:
    with pytest.raises(IsADirectoryError, match="Destination is a directory"):
        FileSink(tmp_path).write(_rendered(), name="book")
