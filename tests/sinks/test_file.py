from pathlib import Path

import pytest

from md_studio.core.convert import RenderedMarkdown
from md_studio.sinks.file import FileSink


def _rendered() -> RenderedMarkdown:
    return RenderedMarkdown(
        text="---\ntitle: T\n---\n## One\n\nBody é\n",
        front_matter="---\ntitle: T\n---\n",
        body="## One\n\nBody é\n",
        chapters=(),
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


def test_file_sink_refuses_symlink_even_with_force(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("keep", encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(target)

    with pytest.raises(OSError, match="Destination is a symlink"):
        FileSink(link, force=True).write(_rendered(), name="book")

    assert link.is_symlink()
    assert target.read_text(encoding="utf-8") == "keep"


def test_file_sink_refuses_dangling_symlink(tmp_path: Path) -> None:
    link = tmp_path / "link.md"
    link.symlink_to(tmp_path / "nowhere.md")

    with pytest.raises(OSError, match="Destination is a symlink"):
        FileSink(link).write(_rendered(), name="book")

    assert not (tmp_path / "nowhere.md").exists()


def test_file_sink_writes_text_without_carriage_returns(tmp_path: Path) -> None:
    dest = tmp_path / "book.md"

    FileSink(dest).write(_rendered(), name="book")

    assert b"\r" not in dest.read_bytes()


def test_file_sink_preserves_carriage_returns_in_text(tmp_path: Path) -> None:
    dest = tmp_path / "book.md"
    rendered = RenderedMarkdown(text="a\r\nb\n", front_matter="", body="a\r\nb\n", chapters=())

    FileSink(dest).write(rendered, name="book")

    assert dest.read_bytes() == b"a\r\nb\n"


def _fail_midway(path: Path, payload: bytes) -> None:
    path.write_bytes(payload[:3])
    raise OSError("disk full")


def test_file_sink_force_failure_keeps_original_and_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "book.md"
    dest.write_text("old", encoding="utf-8")

    monkeypatch.setattr("md_studio.sinks.file._write_exclusive", _fail_midway)

    with pytest.raises(OSError, match="disk full"):
        FileSink(dest, force=True).write(_rendered(), name="book")

    assert dest.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.iterdir()) == [dest]


def test_file_sink_force_keeps_existing_permissions(tmp_path: Path) -> None:
    dest = tmp_path / "book.md"
    dest.write_text("old", encoding="utf-8")
    dest.chmod(0o640)

    FileSink(dest, force=True).write(_rendered(), name="book")

    assert dest.stat().st_mode & 0o777 == 0o640


def test_file_sink_rejects_destination_below_a_file(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")

    with pytest.raises(OSError, match="blocker"):
        FileSink(blocker / "x.md").write(_rendered(), name="book")
