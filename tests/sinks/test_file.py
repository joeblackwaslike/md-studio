import errno
import os
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


def _fail_midway(descriptor: int, payload: bytes) -> None:
    os.write(descriptor, payload[:3])
    os.close(descriptor)
    raise OSError("disk full")


def test_file_sink_force_failure_keeps_original_and_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "book.md"
    dest.write_text("old", encoding="utf-8")

    monkeypatch.setattr("md_studio.sinks.file._fill", _fail_midway)

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


def test_file_sink_create_failure_removes_partial_file_and_allows_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "book.md"
    monkeypatch.setattr("md_studio.sinks.file._fill", _fail_midway)

    with pytest.raises(OSError, match="disk full"):
        FileSink(dest).write(_rendered(), name="book")

    assert not dest.exists()
    monkeypatch.undo()
    FileSink(dest).write(_rendered(), name="book")
    assert dest.read_text(encoding="utf-8") == _rendered().text


class _Interrupted(BaseException):  # noqa: WPS418
    """Stands in for KeyboardInterrupt."""


def _interrupt_midway(descriptor: int, payload: bytes) -> None:
    os.write(descriptor, payload[:3])
    os.close(descriptor)
    raise _Interrupted


def test_file_sink_force_interrupt_keeps_original_and_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "book.md"
    dest.write_text("old", encoding="utf-8")
    monkeypatch.setattr("md_studio.sinks.file._fill", _interrupt_midway)

    with pytest.raises(_Interrupted):
        FileSink(dest, force=True).write(_rendered(), name="book")

    assert dest.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.iterdir()) == [dest]


def test_file_sink_create_interrupt_leaves_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "book.md"
    monkeypatch.setattr("md_studio.sinks.file._fill", _interrupt_midway)

    with pytest.raises(_Interrupted):
        FileSink(dest).write(_rendered(), name="book")

    assert not dest.exists()


def _unlink_denied(self: Path, missing_ok: bool = False) -> None:  # noqa: FBT001, FBT002
    raise PermissionError("unlink denied")


@pytest.mark.parametrize("force", [False, True])
def test_file_sink_failed_cleanup_does_not_mask_the_original_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    force: bool,  # noqa: FBT001
) -> None:
    dest = tmp_path / "book.md"
    monkeypatch.setattr("md_studio.sinks.file._fill", _fail_midway)
    monkeypatch.setattr(Path, "unlink", _unlink_denied)

    with pytest.raises(OSError, match="disk full"):
        FileSink(dest, force=force).write(_rendered(), name="book")


def _emfile(path: Path, mode: int) -> int:
    raise OSError(errno.EMFILE, "Too many open files")


@pytest.mark.parametrize("force", [False, True])
def test_file_sink_open_failure_leaves_existing_destination_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    force: bool,  # noqa: FBT001
) -> None:
    dest = tmp_path / "book.md"
    dest.write_bytes(b"sentinel")
    monkeypatch.setattr("md_studio.sinks.file._create_exclusive", _emfile)

    with pytest.raises(OSError, match="Too many open files"):
        FileSink(dest, force=force).write(_rendered(), name="book")

    assert dest.read_bytes() == b"sentinel"
    assert list(tmp_path.iterdir()) == [dest]


def test_file_sink_force_replaces_destination_with_a_maximum_length_name(
    tmp_path: Path,
) -> None:
    dest = tmp_path / f"{'a' * 247}.md"
    dest.write_text("old", encoding="utf-8")

    FileSink(dest, force=True).write(_rendered(), name="book")

    assert dest.read_text(encoding="utf-8") == _rendered().text
    assert list(tmp_path.iterdir()) == [dest]


class _ModeSpy:
    """Stand-in for ``_fill`` that records each descriptor's permission bits."""

    def __init__(self) -> None:
        self.modes: list[int] = []

    def __call__(self, descriptor: int, payload: bytes) -> None:
        self.modes.append(os.fstat(descriptor).st_mode & 0o777)
        os.write(descriptor, payload)
        os.close(descriptor)


def test_file_sink_stages_replacement_privately_then_matches_destination_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "book.md"
    dest.write_text("old", encoding="utf-8")
    dest.chmod(0o644)
    spy = _ModeSpy()
    monkeypatch.setattr("md_studio.sinks.file._fill", spy)

    FileSink(dest, force=True).write(_rendered(), name="book")

    assert spy.modes == [0o600]
    assert dest.stat().st_mode & 0o777 == 0o644
