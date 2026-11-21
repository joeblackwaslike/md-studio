import importlib
import logging
from pathlib import Path

import pytest
from typer.testing import CliRunner

from md_studio.cli import app
from md_studio.core.convert import convert
from md_studio.core.extensions.base import MarkdownExtension
from md_studio.readers.epub import read_epub
from tests.readers._epub import ChapterSpec, build_epub


def _epub(tmp_path: Path) -> Path:
    specs = [ChapterSpec("Chapter One", "<h1>Chapter One</h1><p>Hello.</p>")]
    return build_epub(tmp_path / "book.epub", "Sample", specs)


def _convert(*args: Path | str):
    return CliRunner().invoke(app, ["convert", *map(str, args)])


def test_cli_converts_epub_fixture(tmp_path: Path) -> None:
    outcome = _convert(_epub(tmp_path))

    assert outcome.exit_code == 0, outcome.output
    output = tmp_path / "book.md"
    assert output.exists()
    assert "Chapter One" in output.read_text(encoding="utf-8")


def test_cli_refuses_overwrite_unless_forced(tmp_path: Path) -> None:
    source = _epub(tmp_path)
    dest = tmp_path / "out" / "x.md"

    first = _convert(source, "-o", dest)
    second = _convert(source, "-o", dest)
    forced = _convert(source, "-o", dest, "--force")

    assert first.exit_code == 0
    assert second.exit_code == 1
    assert "Refusing to overwrite" in second.output
    assert forced.exit_code == 0


def test_cli_reports_unknown_extension(tmp_path: Path) -> None:
    outcome = _convert(_epub(tmp_path), "--ext", "nope")

    assert outcome.exit_code == 1
    assert "nope" in outcome.output


def test_cli_reports_read_error(tmp_path: Path) -> None:
    broken = tmp_path / "broken.epub"
    broken.write_text("not a zip", encoding="utf-8")

    outcome = _convert(broken)

    assert outcome.exit_code == 1
    assert outcome.output.startswith("Error:")
    assert len(outcome.output.strip().splitlines()) == 1
    assert not (tmp_path / "broken.md").exists()


def test_cli_rejects_unsupported_suffix(tmp_path: Path) -> None:
    source = tmp_path / "book.pdf"
    source.write_bytes(b"%PDF")

    outcome = _convert(source)

    assert outcome.exit_code == 1
    assert "Unsupported source type" in outcome.output
    assert outcome.output.startswith("Error:")
    assert len(outcome.output.strip().splitlines()) == 1


def test_cli_reports_unwritable_destination_as_one_line_error(  # noqa: WPS118
    tmp_path: Path,
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")

    outcome = _convert(_epub(tmp_path), "-o", blocker / "x.md")

    assert outcome.exit_code == 1
    assert "Traceback" not in outcome.output
    assert len(outcome.output.strip().splitlines()) == 1
    assert outcome.output.startswith("Error:")


def test_cli_reports_directory_dest_cleanly(tmp_path: Path) -> None:
    outcome = _convert(_epub(tmp_path), "-o", tmp_path, "--force")

    assert outcome.exit_code == 1
    assert "Traceback" not in outcome.output
    assert len(outcome.output.strip().splitlines()) == 1


@pytest.mark.parametrize("raw", ["", ",", " ", " , "])
def test_cli_rejects_ext_without_names(tmp_path: Path, raw: str) -> None:
    outcome = _convert(_epub(tmp_path), "--ext", raw)

    assert outcome.exit_code == 1
    assert outcome.output.startswith("Error:")
    assert len(outcome.output.strip().splitlines()) == 1
    assert not (tmp_path / "book.md").exists()


def test_cli_ext_tolerates_spaces_and_trailing_comma(tmp_path: Path) -> None:
    source = _epub(tmp_path)
    expected = convert(read_epub(source), extensions=["fix-headings", "remove-footnotes"]).text

    outcome = _convert(source, "--ext", "fix-headings, remove-footnotes,")

    assert outcome.exit_code == 0, outcome.output
    assert (tmp_path / "book.md").read_text(encoding="utf-8") == expected


def test_cli_reports_missing_source_as_one_line_error(tmp_path: Path) -> None:
    outcome = _convert(tmp_path / "missing.epub")

    assert outcome.exit_code == 1
    assert outcome.output.startswith("Error:")
    assert len(outcome.output.strip().splitlines()) == 1


def test_cli_refuses_output_that_is_the_source(tmp_path: Path) -> None:
    source = _epub(tmp_path)
    original = source.read_bytes()

    outcome = _convert(source, "-o", source, "--force")

    assert outcome.exit_code == 1
    assert outcome.output.startswith("Error:")
    assert "source" in outcome.output
    assert source.read_bytes() == original


def test_cli_refuses_aliased_source_output(tmp_path: Path) -> None:
    source = _epub(tmp_path)
    alias = tmp_path / "sub" / ".." / source.name

    outcome = _convert(source, "-o", alias, "--force")

    assert outcome.exit_code == 1
    assert "source" in outcome.output


def test_cli_reports_epub_without_chapters_as_one_line_error(tmp_path: Path) -> None:
    empty = build_epub(tmp_path / "empty.epub", "Empty", [])

    outcome = _convert(empty)

    assert outcome.exit_code == 1
    assert "Traceback" not in outcome.output
    assert outcome.output.startswith("Error:")
    assert len(outcome.output.strip().splitlines()) == 1


def test_cli_reports_symlink_loop_output_as_one_line_error(tmp_path: Path) -> None:
    loop = tmp_path / "loop.md"
    loop.symlink_to(loop)

    outcome = _convert(_epub(tmp_path), "-o", loop, "--force")

    assert outcome.exit_code == 1
    assert "Traceback" not in outcome.output
    assert outcome.output.startswith("Error:")
    assert len(outcome.output.strip().splitlines()) == 1


def test_cli_reports_unresolvable_output_path_as_one_line_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _epub(tmp_path)
    monkeypatch.setattr(Path, "resolve", _raise_loop)

    outcome = _convert(source, "-o", tmp_path / "out.md")

    assert outcome.exit_code == 1
    assert "Traceback" not in outcome.output
    assert outcome.output.startswith("Error:")
    assert len(outcome.output.strip().splitlines()) == 1


def _raise_loop(self: Path, strict: bool = False) -> Path:  # noqa: FBT001, FBT002
    raise RuntimeError(f"Symlink loop from {self}")


class _BrokenEntryPoint:
    name = "broken"

    def load(self) -> None:
        raise ImportError("boom: missing dependency")


def _install_broken_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "md_studio.core.extensions.discovery.entry_points", lambda group: [_BrokenEntryPoint()]
    )


def test_cli_reports_failed_extension_load_as_one_clean_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _install_broken_plugin(monkeypatch)

    outcome = _convert(_epub(tmp_path), "--ext", "broken")

    assert outcome.exit_code == 1
    assert "Traceback" not in outcome.output
    assert outcome.output.startswith("Error: extension 'broken' failed to load")
    assert len(outcome.output.strip().splitlines()) == 1
    assert all(record.levelno < logging.WARNING for record in caplog.records)


def test_cli_conversion_ignores_unrelated_broken_plugin_quietly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _install_broken_plugin(monkeypatch)

    outcome = _convert(_epub(tmp_path))

    assert outcome.exit_code == 0, outcome.output
    assert "Traceback" not in outcome.output
    assert all(record.levelno < logging.WARNING for record in caplog.records)


def _replace_denied(source: Path, target: Path) -> None:
    raise PermissionError("replace denied")


def test_cli_reports_failed_atomic_replace_as_one_line_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "out.md"
    dest.write_bytes(b"original")
    monkeypatch.setattr("md_studio.sinks.file.os.replace", _replace_denied)

    outcome = _convert(_epub(tmp_path), "-o", dest, "--force")

    assert outcome.exit_code == 1
    assert outcome.output.startswith("Error:")
    assert len(outcome.output.strip().splitlines()) == 1
    assert dest.read_bytes() == b"original"


class _LazyEntryPoint:
    name = "lazy"

    def load(self) -> type[MarkdownExtension]:
        return _LazyImportExtension


class _LazyImportExtension(MarkdownExtension):
    name = "lazy"

    def __init__(self) -> None:
        importlib.import_module("md_studio_missing_module")


def test_cli_reports_extension_construction_import_error_as_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "md_studio.core.extensions.discovery.entry_points", lambda group: [_LazyEntryPoint()]
    )

    outcome = _convert(_epub(tmp_path), "--ext", "lazy")

    assert outcome.exit_code == 1
    assert "Traceback" not in outcome.output
    assert outcome.output.startswith("Error: extension 'lazy' failed to load")
    assert len(outcome.output.strip().splitlines()) == 1


def _distinct_gid(path: Path) -> int:
    return 1 if path.name.startswith(".md-studio-") else 2


def _chown_denied(path: Path, uid: int, gid: int) -> None:
    raise PermissionError("not a member")


def test_cli_reports_unpreservable_group_as_one_line_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "out.md"
    dest.write_bytes(b"original")
    monkeypatch.setattr("md_studio.sinks.file._gid", _distinct_gid)
    monkeypatch.setattr("md_studio.sinks.file.os.chown", _chown_denied)

    outcome = _convert(_epub(tmp_path), "-o", dest, "--force")

    assert outcome.exit_code == 1
    assert outcome.output.startswith("Error: Cannot preserve group of")
    assert len(outcome.output.strip().splitlines()) == 1
    assert dest.read_bytes() == b"original"
