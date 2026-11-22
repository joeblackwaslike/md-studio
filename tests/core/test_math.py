"""Tests for math IR nodes and their Markdown rendering."""

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from md_studio.core import ir
from md_studio.core.convert import convert
from md_studio.core.headings import text_of_inlines
from md_studio.core.render import Renderer, render_inlines
from md_studio.core.render.blocks import render_block_string
from md_studio.readers.epub import read_epub
from tests.readers._epub import ChapterSpec, build_epub


def _body(*chapters: ir.ChapterIR, has_math: bool = False) -> str:
    return Renderer(has_math=has_math).render(chapters).body


def _para(*nodes: ir.Inline) -> ir.Paragraph:
    return ir.Paragraph(nodes)


def test_inline_math_renders_dollars() -> None:
    assert render_inlines((ir.Math("x^2"),)) == "$x^2$"


def test_block_math_renders_fenced_dollars() -> None:
    assert render_block_string(ir.MathBlock("x + y")) == "$$\nx + y\n$$"


def test_math_content_not_escaped() -> None:
    rendered = render_inlines((ir.Math(r"a_b \\ `c`"),))
    assert rendered == r"$a_b \\ `c`$"


def test_inline_math_newlines_become_spaces() -> None:
    assert render_inlines((ir.Math("a\nb\r\nc"),)) == "$a b  c$"


def test_empty_inline_math_renders_nothing() -> None:
    assert render_inlines((ir.Text("a"), ir.Math(""), ir.Math(" \n "), ir.Text("b"))) == "ab"


def test_empty_block_math_renders_nothing() -> None:
    assert render_block_string(ir.MathBlock("  \n")) == ""


def test_dollar_in_prose_escaped_only_with_has_math() -> None:
    chapter = ir.ChapterIR("C", (_para(ir.Text("costs $5"), ir.Math("x")),))
    assert r"costs \$5$x$" in _body(chapter, has_math=True)
    assert "costs $5$x$" in _body(chapter, has_math=False)


def test_dollar_escaping_does_not_leak_between_renders() -> None:
    chapter = ir.ChapterIR("C", (_para(ir.Text("$5")),))
    _body(chapter, has_math=True)
    assert "$5" in _body(chapter)
    assert r"\$5" not in _body(chapter)


def test_dollar_in_code_span_never_escaped() -> None:
    chapter = ir.ChapterIR("C", (_para(ir.CodeSpan("$HOME")),))
    assert "`$HOME`" in _body(chapter, has_math=True)


def test_math_block_keeps_blank_line_separation_and_offsets() -> None:
    chapters = (
        ir.ChapterIR("One", (_para(ir.Text("a")), ir.MathBlock("x"), _para(ir.Text("b")))),
        ir.ChapterIR("Two", (ir.MathBlock("y"),)),
    )
    rendered = Renderer().render(chapters)
    body = rendered.body

    assert body == "## One\n\na\n\n$$\nx\n$$\n\nb\n\n## Two\n\n$$\ny\n$$\n"
    for offset, title in zip(rendered.offsets, ("One", "Two"), strict=True):
        assert body.encode()[offset.byte :].decode().startswith(f"## {title}")
        assert body.split("\n")[offset.line - 1] == f"## {title}"


def test_epub_output_unchanged_without_math(tmp_path: Path) -> None:
    path = build_epub(tmp_path / "d.epub", "D", [ChapterSpec("C", "<p>cost $5 and $6</p>")])
    assert "cost $5 and $6" in convert(read_epub(path)).body


def test_math_contributes_its_tex_to_plain_text() -> None:
    assert text_of_inlines((ir.Text("a "), ir.Math("x^2"))) == "a x^2"


@pytest.mark.parametrize(
    ("tex", "expected"),
    [
        ("a$b", r"$a\$b$"),
        (r"a\$b", r"$a\$b$"),
        (r"a\\$b", r"$a\\\$b$"),
        (r"a\\\$b", r"$a\\\$b$"),
        (" x ", "$x$"),
        ("\n x\n", "$x$"),
    ],
)
def test_inline_math_contract(tex: str, expected: str) -> None:
    assert render_inlines((ir.Math(tex),)) == expected


def test_block_math_cannot_close_early() -> None:
    lines = render_block_string(ir.MathBlock("a\n$$\nb")).split("\n")
    assert lines == ["$$", "a", r"\$\$", "b", "$$"]


def test_block_math_strips_surrounding_whitespace() -> None:
    assert render_block_string(ir.MathBlock("\n  x  \n")) == "$$\nx\n$$"


def test_convert_escapes_prose_dollars_only_when_document_has_math(tmp_path: Path) -> None:
    path = build_epub(tmp_path / "m.epub", "M", [ChapterSpec("C", "<p>cost $5</p>")])
    document = read_epub(path)

    assert r"cost \$5" in convert(replace(document, has_math=True)).body
    assert r"\$" not in convert(replace(document, has_math=False)).body


def test_dollar_escaping_resets_after_a_failed_render() -> None:
    broken = ir.ChapterIR("C", (ir.Paragraph(cast("tuple[ir.Inline, ...]", None)),))
    with pytest.raises(TypeError):
        Renderer(has_math=True).render((broken,))

    assert r"\$" not in _body(ir.ChapterIR("C", (_para(ir.Text("$5")),)))


@pytest.mark.parametrize("count", [1, 2, 3])
def test_math_ending_in_backslashes_still_closes(count: int) -> None:
    tail = "\\" * count
    pad = " " if count % 2 else ""
    assert render_inlines((ir.Math(f"x{tail}"),)) == f"$x{tail}{pad}$"
    assert render_block_string(ir.MathBlock(f"x{tail}")) == f"$$\nx{tail}{pad}\n$$"


def test_block_math_drops_blank_lines() -> None:
    assert render_block_string(ir.MathBlock("a\n\n \nb")) == "$$\na\nb\n$$"


def test_math_in_table_cell_escapes_pipe() -> None:
    cell = (ir.TableCell((ir.Math("a|b"),)),)
    assert render_block_string(ir.Table(cell, ())).split("\n") == [r"| $a\|b$ |", "| --- |"]


def test_math_in_heading() -> None:
    assert (
        render_block_string(ir.Heading(2, (ir.Text("E = "), ir.Math("mc^2")))) == "### E = $mc^2$"
    )


def test_math_in_list_item() -> None:
    entry = ir.ListItem((ir.Paragraph((ir.Math("x"),)),))
    assert render_block_string(ir.ListBlock(ordered=False, items=(entry,))) == "- $x$"
