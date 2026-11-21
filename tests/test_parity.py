"""Byte-for-byte parity of md-studio output with the safaribooks Markdown pipeline.

The committed goldens under ``tests/fixtures/parity`` were generated once from
safaribooks commit ``4211efe``. The unconditional test compares against them; the
optional live test regenerates the baseline output from a checkout named by
``SAFARIBOOKS_BASELINE``.
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

from md_studio.cli import app
from tests.readers._epub import ChapterSpec, build_epub

BASELINE = os.environ.get("SAFARIBOOKS_BASELINE")
BASELINE_SHA = "4211efe"
GOLDEN_DIR = Path(__file__).parent / "fixtures" / "parity"

_SCRIPT = """
import sys
from pathlib import Path
from safaribooks.core.markdown.convert import convert_epub

names = sys.argv[3].split(",") if sys.argv[3] else None
convert_epub(Path(sys.argv[1]), Path(sys.argv[2]), extensions=names)
"""

_WITH_FLAGS = ("--with", "lxml")

_FOOTNOTES_BODY = (
    '<div xmlns:epub="http://www.idpf.org/2007/ops">'
    '<p>A claim<sup><a href="#fn1" epub:type="noteref">1</a></sup> needs a source.</p>'
    '<aside id="fn1" epub:type="footnote"><p>The source, with <em>detail</em>.</p></aside>'
    "</div>"
)

_TABLE_BODY = (
    "<table><thead><tr><th>Name</th><th>Qty</th></tr></thead>"
    "<tbody><tr><td>Widget</td><td>3</td></tr><tr><td>Gadget</td><td>12</td></tr></tbody>"
    "</table>"
    "<blockquote><p>Quoted text spanning a line.</p></blockquote>"
)

_LISTS_BODY = (
    "<ul><li>Outer one<ul><li>Inner a</li><li>Inner b</li></ul></li><li>Outer two</li></ul>"
    '<p>Go <a href="ch1.xhtml">back</a> or follow a <a href="missing.xhtml#x">dead link</a>.</p>'
)

_UNICODE_BODY = (
    '<p>Naïve façade — “quotes” 日本語 ☕.</p><pre><code>def f():\n    return "é"\n</code></pre>'
)

RICH_SPECS = (
    ChapterSpec(
        "Contents",
        '<ul><li><a href="ch1.xhtml">Redundant Heading</a></li>'
        '<li><a href="ch2.xhtml">Tables</a></li></ul>',
    ),
    ChapterSpec(
        "Redundant Heading",
        "<h1>Redundant Heading</h1><h2>Sub heading</h2>"
        "<p>Inline <em>emphasis</em>, <strong>strong</strong> and <code>code()</code>.</p>",
    ),
    ChapterSpec("Tables", _TABLE_BODY),
    ChapterSpec("Lists and Links", _LISTS_BODY),
    ChapterSpec("Footnotes", _FOOTNOTES_BODY),
    ChapterSpec("Café ☕ Notes", _UNICODE_BODY),
    ChapterSpec("Empty", ""),
)

ALL_EXTENSIONS = "fix-headings,remove-footnotes,fix-broken-links,reformat-toc"


@dataclass(frozen=True)
class ParityCase:
    """A named conversion scenario and the extensions it enables."""

    name: str
    extensions: str


CASES = (
    pytest.param(ParityCase("rich", ""), id="rich"),
    pytest.param(ParityCase("rich-extensions", ALL_EXTENSIONS), id="rich-extensions"),
)


def _rich_epub(tmp_path: Path) -> Path:
    return build_epub(tmp_path / "book.epub", "Parity Book", list(RICH_SPECS))


def _studio_markdown(epub: Path, out: Path, extensions: str) -> bytes:
    arguments = ["convert", str(epub), "-o", str(out)]
    if extensions:
        arguments += ["--ext", extensions]
    outcome = CliRunner().invoke(app, arguments)
    assert outcome.exit_code == 0, outcome.output
    return out.read_bytes()


def _baseline_markdown(baseline: Path, epub: Path, out: Path, extensions: str) -> bytes:
    script = out.parent / "run.py"
    script.write_text(_SCRIPT, encoding="utf-8")
    command = ["uv", "run", "--no-project", "--python", sys.executable, *_WITH_FLAGS]
    command += ["python", str(script), str(epub), str(out), extensions]
    env = {**os.environ, "PYTHONPATH": str(baseline / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run(command, check=True, env=env, cwd=out.parent)
    return out.read_bytes()


def _baseline_head(baseline: Path) -> str:
    done = subprocess.run(
        ["git", "-C", str(baseline), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


@pytest.mark.parametrize("case", CASES)
def test_output_matches_committed_baseline_golden(tmp_path: Path, case: ParityCase) -> None:
    golden = (GOLDEN_DIR / f"{case.name}.md").read_bytes()

    actual = _studio_markdown(_rich_epub(tmp_path), tmp_path / "out.md", case.extensions)

    assert actual == golden


@pytest.mark.skipif(not BASELINE, reason="SAFARIBOOKS_BASELINE not set")
@pytest.mark.parametrize("case", CASES)
def test_output_matches_safaribooks_baseline(tmp_path: Path, case: ParityCase) -> None:
    baseline = Path(str(BASELINE))
    assert _baseline_head(baseline).startswith(BASELINE_SHA)
    epub = _rich_epub(tmp_path)
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()

    expected = _baseline_markdown(baseline, epub, baseline_dir / "book.md", case.extensions)
    actual = _studio_markdown(epub, tmp_path / "out.md", case.extensions)

    assert actual == expected
