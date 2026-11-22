"""The CLI reports lost CSS as warnings and always reports the promotion count."""

from pathlib import Path

from typer.testing import CliRunner

from md_studio.cli import app
from tests.readers._epub import (
    ChapterSpec,
    build_css_headings_epub,
    build_epub,
    corrupt_first_stylesheet,
)

_BODY = '<div class="class-part">Part One</div>'


def _run(*args: Path | str):
    return CliRunner().invoke(app, ["convert", *map(str, args)])


def _epub(tmp_path: Path, *sheets: str) -> Path:
    specs = [ChapterSpec("Chapter One", _BODY)]
    return build_epub(tmp_path / "b.epub", "B", specs, stylesheets=sheets)


def test_corrupt_css_member_warns_with_fix_headings_and_exits_zero(tmp_path: Path) -> None:
    styled = _epub(tmp_path, ".class-part{font-size:2.333rem}")
    broken = corrupt_first_stylesheet(styled, tmp_path / "broken.epub")

    outcome = _run(broken, "--ext", "fix-headings")

    assert outcome.exit_code == 0, outcome.output
    assert "warning: CSS member OEBPS/css/s0.css was skipped" in outcome.output
    assert "Promoted 0 headings" in outcome.output


def test_corrupt_css_member_is_silent_without_the_extension(tmp_path: Path) -> None:
    styled = _epub(tmp_path, ".class-part{font-size:2.333rem}")
    broken = corrupt_first_stylesheet(styled, tmp_path / "broken.epub")

    outcome = _run(broken)

    assert outcome.exit_code == 0, outcome.output
    assert "warning" not in outcome.output
    assert "Promoted" not in outcome.output


def test_corrupt_css_member_is_silent_for_extensions_that_ignore_css(tmp_path: Path) -> None:
    styled = _epub(tmp_path, ".class-part{font-size:2.333rem}")
    broken = corrupt_first_stylesheet(styled, tmp_path / "broken.epub")

    outcome = _run(broken, "--ext", "remove-footnotes")

    assert outcome.exit_code == 0, outcome.output
    assert "warning" not in outcome.output


def test_budget_truncation_warns(tmp_path: Path) -> None:
    source = _epub(tmp_path, f".class-part{{font-size:2.333rem}}{' ' * 2_000_000}")

    outcome = _run(source, "--ext", "fix-headings")

    assert outcome.exit_code == 0, outcome.output
    assert "warning: CSS member OEBPS/css/s0.css was cut" in outcome.output


def test_unclosed_comment_warns_and_keeps_the_rules_before_it(tmp_path: Path) -> None:
    source = _epub(tmp_path, ".class-part{font-size:2.333rem}/* never closed")

    outcome = _run(source, "--ext", "fix-headings")

    assert outcome.exit_code == 0, outcome.output
    assert "warning: stylesheet ends inside an unclosed comment" in outcome.output
    assert "Promoted 1 headings" in outcome.output


def test_clean_conversion_prints_no_warning(tmp_path: Path) -> None:
    source = _epub(tmp_path, ".class-part{font-size:2.333rem}")

    outcome = _run(source, "--ext", "fix-headings")

    assert "warning" not in outcome.output


def test_file_sink_reports_the_promotion_count(tmp_path: Path) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")

    outcome = _run(source, "--ext", "fix-headings")

    assert "Promoted 3 headings" in outcome.output


def test_file_sink_reports_zero_promotions(tmp_path: Path) -> None:
    source = build_epub(tmp_path / "p.epub", "P", [ChapterSpec("One", "<h1>One</h1><p>x</p>")])

    outcome = _run(source, "--ext", "fix-headings")

    assert "Promoted 0 headings" in outcome.output


def test_vault_sink_reports_the_count_and_that_no_audit_is_written(tmp_path: Path) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")
    vault = tmp_path / "vault"
    vault.mkdir()

    outcome = _run(source, "--sink", "obsidian", "--vault", vault, "--ext", "fix-headings")

    assert outcome.exit_code == 0, outcome.output
    assert "Promoted 3 headings (the audit report is not written for --sink obsidian)" in (
        outcome.output
    )


def test_vault_sink_reports_zero_without_the_audit_remark(tmp_path: Path) -> None:
    source = build_epub(tmp_path / "p.epub", "P", [ChapterSpec("One", "<h1>One</h1><p>x</p>")])
    vault = tmp_path / "vault"
    vault.mkdir()

    outcome = _run(source, "--sink", "obsidian", "--vault", vault, "--ext", "fix-headings")

    assert "Promoted 0 headings\n" in outcome.output
    assert "audit" not in outcome.output
