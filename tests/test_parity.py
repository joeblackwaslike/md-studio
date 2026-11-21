import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from md_studio.cli import app
from tests.readers._epub import ChapterSpec, build_epub

BASELINE = os.environ.get("SAFARIBOOKS_BASELINE")

_SCRIPT = """
import sys
from pathlib import Path
from safaribooks.core.markdown.convert import convert_epub

convert_epub(Path(sys.argv[1]), Path(sys.argv[2]))
"""

_WITH_FLAGS = ("--with", "lxml", "--with", "html5lib", "--with", "httpx")


def _baseline_markdown(baseline: Path, epub: Path, out: Path, script: Path) -> bytes:
    script.write_text(_SCRIPT, encoding="utf-8")
    command = ["uv", "run", "--no-project", "--python", sys.executable, *_WITH_FLAGS]
    command += ["python", str(script), str(epub), str(out)]
    env = {**os.environ, "PYTHONPATH": str(baseline / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run(command, check=True, env=env, cwd=out.parent)
    return out.read_bytes()


@pytest.mark.skipif(not BASELINE, reason="SAFARIBOOKS_BASELINE not set")
def test_output_matches_safaribooks_baseline(tmp_path: Path) -> None:
    specs = [
        ChapterSpec(
            "Chapter One",
            "<h1>Chapter One</h1><p>Price is $5 and é.</p><ul><li>a</li></ul>",
        ),
        ChapterSpec("Chapter Two", "<h1>Chapter Two</h1><pre>code()</pre><p>Tail.</p>"),
    ]
    epub = build_epub(tmp_path / "book.epub", "Parity Book", specs)
    baseline_out = tmp_path / "baseline" / "book.md"
    baseline_out.parent.mkdir()

    expected = _baseline_markdown(Path(str(BASELINE)), epub, baseline_out, tmp_path / "run.py")
    outcome = CliRunner().invoke(app, ["convert", str(epub)])

    assert outcome.exit_code == 0, outcome.output
    assert (tmp_path / "book.md").read_bytes() == expected
