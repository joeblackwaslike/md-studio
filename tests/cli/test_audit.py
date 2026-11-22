"""The CLI writes ``<output stem>.audit.md`` only when headings were promoted."""

from pathlib import Path

from typer.testing import CliRunner

from md_studio.cli import app
from tests.readers._epub import ChapterSpec, build_css_headings_epub, build_epub


def _run(*args: Path | str):
    return CliRunner().invoke(app, ["convert", *map(str, args)])


def _audits(root: Path) -> list[Path]:
    return sorted(root.rglob("*.audit.md"))


def test_cli_writes_audit_next_to_output_when_headings_promoted(tmp_path: Path) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")
    dest = tmp_path / "out" / "result.md"

    outcome = _run(source, "-o", dest, "--ext", "fix-headings")

    assert outcome.exit_code == 0, outcome.output
    audit = dest.with_name("result.audit.md")
    assert audit.read_text(encoding="utf-8").count("class-") == 3
    assert str(audit) in outcome.output


def test_cli_writes_no_audit_without_promotions(tmp_path: Path) -> None:
    specs = [ChapterSpec("One", "<h1>One</h1><p>Plain.</p>")]
    source = build_epub(tmp_path / "plain.epub", "Plain", specs)

    outcome = _run(source, "--ext", "fix-headings")

    assert outcome.exit_code == 0, outcome.output
    assert _audits(tmp_path) == []


def test_cli_writes_no_audit_when_extension_not_enabled(tmp_path: Path) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")

    outcome = _run(source)

    assert outcome.exit_code == 0, outcome.output
    assert _audits(tmp_path) == []


def test_cli_audit_respects_force(tmp_path: Path) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")
    audit = tmp_path / "styled.audit.md"
    audit.write_text("old", encoding="utf-8")

    refused = _run(source, "--ext", "fix-headings")
    kept = audit.read_text(encoding="utf-8")
    forced = _run(source, "--ext", "fix-headings", "--force")

    assert refused.exit_code == 1
    assert kept == "old"
    assert forced.exit_code == 0
    assert "Part One" in audit.read_text(encoding="utf-8")


def test_cli_obsidian_sink_ignores_audit(tmp_path: Path) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")
    vault = tmp_path / "vault"
    vault.mkdir()

    outcome = _run(source, "--sink", "obsidian", "--vault", vault, "--ext", "fix-headings")

    assert outcome.exit_code == 0, outcome.output
    assert (vault / "Book Notes" / "styled.md").exists()
    assert _audits(tmp_path) == []


def test_cli_refused_audit_leaves_no_markdown_behind(tmp_path: Path) -> None:
    source = build_css_headings_epub(tmp_path / "styled.epub")
    (tmp_path / "styled.audit.md").write_text("old", encoding="utf-8")

    outcome = _run(source, "--ext", "fix-headings")

    assert outcome.exit_code == 1
    assert "styled.audit.md" in outcome.output
    assert not (tmp_path / "styled.md").exists()
