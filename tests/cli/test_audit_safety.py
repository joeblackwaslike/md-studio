"""The audit report is written with the file sink's safety and clear failure messages."""

import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from md_studio.cli import app
from md_studio.core.convert import convert
from md_studio.core.extensions import audit
from md_studio.readers.epub import read_epub
from md_studio.sinks import file as file_sink
from tests.readers._epub import build_css_headings_epub


def _run(*args: Path | str):
    return CliRunner().invoke(app, ["convert", *map(str, args), "--ext", "fix-headings"])


def test_audit_content_is_exactly_the_rendered_report(tmp_path: Path) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")
    records = convert(read_epub(source), extensions=["fix-headings"]).promotions

    outcome = _run(source)

    assert outcome.exit_code == 0, outcome.output
    assert (tmp_path / "styled.audit.md").read_text(encoding="utf-8") == audit.render(records)


def test_audit_symlink_target_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")
    victim = tmp_path / "victim.txt"
    victim.write_text("keep", encoding="utf-8")
    (tmp_path / "styled.audit.md").symlink_to(victim)

    outcome = _run(source, "--force")

    assert outcome.exit_code == 1
    assert "symlink" in outcome.output
    assert victim.read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "styled.md").exists()


def test_audit_directory_target_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")
    (tmp_path / "styled.audit.md").mkdir()

    outcome = _run(source, "--force")

    assert outcome.exit_code == 1
    assert "directory" in outcome.output
    assert not (tmp_path / "styled.md").exists()


def test_existing_audit_without_force_is_refused_before_the_markdown(tmp_path: Path) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")
    (tmp_path / "styled.audit.md").write_text("old", encoding="utf-8")

    outcome = _run(source)

    assert outcome.exit_code == 1
    assert "Refusing to overwrite" in outcome.output
    assert not (tmp_path / "styled.md").exists()


def test_force_replaces_the_audit_atomically_and_keeps_its_mode(tmp_path: Path) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")
    report = tmp_path / "styled.audit.md"
    report.write_text("old", encoding="utf-8")
    report.chmod(0o640)

    outcome = _run(source, "--force")

    assert outcome.exit_code == 0, outcome.output
    assert "Heading promotions" in report.read_text(encoding="utf-8")
    assert stat.S_IMODE(report.stat().st_mode) == 0o640
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "styled.audit.md",
        "styled.epub",
        "styled.md",
    ]


def _staging_files(directory: Path) -> list[str]:
    return [path.name for path in directory.iterdir() if path.name.startswith(".md-studio-")]


def _failing_replace(source: str, destination: str) -> None:
    raise OSError(28, "No space left on device")


def test_failed_audit_replace_keeps_the_original_and_names_the_written_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")
    report = tmp_path / "styled.audit.md"
    report.write_text("old", encoding="utf-8")
    monkeypatch.setattr(file_sink.os, "replace", _failing_replace)

    outcome = _run(source, "--force")

    assert outcome.exit_code == 1
    assert f"wrote {tmp_path / 'styled.md'} but audit failed" in outcome.output
    assert "No space left" in outcome.output
    assert (tmp_path / "styled.md").exists()
    assert (report.read_text(encoding="utf-8"), _staging_files(tmp_path)) == ("old", [])


def test_destination_without_a_file_name_is_a_clean_one_line_error(tmp_path: Path) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")

    outcome = _run(source, "-o", "/")

    assert outcome.exit_code == 1
    assert outcome.output.startswith("Error: ")
    assert "Traceback" not in outcome.output
    assert len(outcome.output.strip().splitlines()) == 1
