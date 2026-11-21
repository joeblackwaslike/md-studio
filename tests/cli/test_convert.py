from pathlib import Path

import pytest

from tests.readers._epub import ChapterSpec, build_epub

app = pytest.importorskip("md_studio.cli").app
CliRunner = pytest.importorskip("typer.testing").CliRunner


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
    assert not (tmp_path / "broken.md").exists()


def test_cli_rejects_unsupported_suffix(tmp_path: Path) -> None:
    source = tmp_path / "book.pdf"
    source.write_bytes(b"%PDF")

    outcome = _convert(source)

    assert outcome.exit_code != 0
    assert ".epub" in outcome.output


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
