"""Strikethrough inline node: extraction of del/s/strike and ``~~`` rendering."""

from pathlib import Path

import pytest
from lxml import html

from md_studio.core import ir
from md_studio.core.convert import convert
from md_studio.core.extensions import ExtCtx, RemoveFootnotes
from md_studio.core.extract import blocks_from_element
from md_studio.core.render.inlines import render_inlines
from md_studio.readers.epub import read_epub
from tests.readers._epub import ChapterSpec, build_epub


def _paragraph(fragment: str) -> ir.Paragraph:
    blocks = blocks_from_element(html.fromstring(f"<div>{fragment}</div>"))
    paragraph = blocks[0]
    assert isinstance(paragraph, ir.Paragraph)
    return paragraph


def _body(tmp_path: Path, fragment: str) -> str:
    specs = [ChapterSpec("One", f"<p>{fragment}</p>")]
    epub = build_epub(tmp_path / "b.epub", "T", specs)
    return convert(read_epub(epub)).body


@pytest.mark.parametrize("tag", ["del", "s", "strike"])
def test_strike_tags_extract_to_strikethrough(tag: str) -> None:
    paragraph = _paragraph(f"<p>a <{tag}>b</{tag}> c</p>")

    assert paragraph.children == (
        ir.Text("a "),
        ir.Strikethrough((ir.Text("b"),)),
        ir.Text(" c"),
    )


def test_strikethrough_renders_tildes(tmp_path: Path) -> None:
    body = _body(tmp_path, "keep <del>drop</del> <s>this</s> <strike>too</strike>")

    assert "keep ~~drop~~ ~~this~~ ~~too~~" in body


def test_strikethrough_renders_nested_formatting_and_escapes_text() -> None:
    node = ir.Strikethrough((ir.Emphasis((ir.Text("a"),)), ir.Text(" `b`")))

    assert render_inlines((node,)) == r"~~*a* \`b\`~~"


@pytest.mark.parametrize("fragment", ["<del></del>", "<s> </s>", "<strike><br/></strike>x"])
def test_empty_strikethrough_renders_nothing(fragment: str) -> None:
    rendered = render_inlines(_paragraph(f"<p>[{fragment}]</p>").children)

    assert "~" not in rendered


def test_strikethrough_text_counts_toward_heading_text(tmp_path: Path) -> None:
    specs = [ChapterSpec("One", "<h2>Old <del>name</del></h2>")]
    epub = build_epub(tmp_path / "b.epub", "T", specs)

    assert "### Old ~~name~~" in convert(read_epub(epub)).body


def test_footnote_refs_inside_strikethrough_are_removed() -> None:
    struck = ir.Strikethrough((ir.Text("x"), ir.FootnoteRef("fn1")))
    chapter = ir.ChapterIR(title="C", blocks=(ir.Paragraph((struck,)),))

    transformed = RemoveFootnotes().transform_chapter(chapter, ExtCtx(book=ir.BookMeta(title="B")))

    paragraph = transformed.blocks[0]
    assert isinstance(paragraph, ir.Paragraph)
    assert paragraph.children == (ir.Strikethrough((ir.Text("x"),)),)


def test_sup_and_sub_render_as_plain_text_today(tmp_path: Path) -> None:
    body = _body(tmp_path, "H<sub>2</sub>O and x<sup>2</sup>")

    assert "H2O and x2" in body


def test_strikethrough_wrapping_a_link_and_an_image(tmp_path: Path) -> None:
    body = _body(tmp_path, '<s><a href="http://u">t</a></s> <s><img alt="pic" src="x.png"/></s>')

    assert "~~[t](http://u)~~ ~~pic~~" in body


def test_del_inside_code_adds_no_tildes_today(tmp_path: Path) -> None:
    specs = [ChapterSpec("One", "<pre>a <del>b</del> c</pre><p><code>x<del>y</del></code></p>")]
    epub = build_epub(tmp_path / "b.epub", "T", specs)

    body = convert(read_epub(epub)).body

    assert "a b c" in body
    assert "`xy`" in body
    assert "~" not in body


def test_padded_strikethrough_keeps_its_padding_today(tmp_path: Path) -> None:
    body = _body(tmp_path, "a<del> x </del>b")

    assert "a~~ x ~~b" in body


def test_strikethrough_nests_with_emphasis_either_way_round(tmp_path: Path) -> None:
    body = _body(tmp_path, "<s><em>x</em></s> <em><s>y</s></em>")

    assert "~~*x*~~ *~~y~~*" in body


def test_strike_holding_only_a_removed_noteref_renders_nothing(tmp_path: Path) -> None:
    fragment = (
        '<p>a<del><a class="noteref" href="#fn1">1</a></del>b</p>'
        '<aside id="fn1" class="footnote"><p>note</p></aside>'
    )
    epub = build_epub(tmp_path / "b.epub", "T", [ChapterSpec("One", fragment)])

    body = convert(read_epub(epub), extensions=["remove-footnotes"]).body

    assert "ab" in body
    assert "~" not in body
    assert "[^" not in body
