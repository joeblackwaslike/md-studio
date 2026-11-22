"""Review fixes for the LaTeXML source fix: ordering, hostile input, chapterless papers, limits."""

import re
from dataclasses import replace
from pathlib import Path

import pytest
from lxml import etree
from lxml import html as lxml_html

from md_studio.core.convert import convert
from md_studio.core.document import Document, DocumentMetadata, SourceChapter
from md_studio.core.exceptions import ReadError
from md_studio.extractors.arxiv_latexml import LatexmlFix
from md_studio.extractors.latexml_text import plain_text
from md_studio.readers.html import read_html
from tests.extractors.linear import assert_linear
from tests.extractors.test_arxiv_latexml import PAPER, _page

ARTICLE = Path(__file__).parents[1] / "fixtures" / "latexml_article.html"
NOTE = (
    '<span id="{ident}" class="ltx_note ltx_role_footnote"><sup class="ltx_note_mark">1</sup>'
    '<span class="ltx_note_outer"><span class="ltx_note_content">{text}</span></span></span>'
)


def _chapter(body: str, tmp_path: Path, title: str = "One") -> Document:
    wrapped = (
        f'<section id="Ch1" class="ltx_chapter"><h3 class="ltx_title ltx_title_chapter">{title}</h3>'
        f"{body}</section>"
    )
    document = _page(wrapped, tmp_path=tmp_path)
    return replace(document, metadata=replace(document.metadata, source_file=PAPER))


def _md(document: Document) -> str:
    return convert(document, extensions=["arxiv-latexml"]).body


def test_footnote_text_stays_out_of_chapter_and_section_headings(tmp_path: Path) -> None:
    note = NOTE.format(ident="n1", text="LEAKED")
    body = (
        f'<section id="S1" class="ltx_section"><h4 class="ltx_title ltx_title_section">Part{note}'
        '</h4><div class="ltx_para"><p class="ltx_p">see <a href="#S1">there</a></p></div></section>'
    )
    document = _chapter(body, tmp_path, title=f"Basics{note}")

    fixed = LatexmlFix().apply(document)
    text = _md(document)

    assert [chapter.title for chapter in fixed.chapters] == ["Basics"]
    assert "\n### Part\n" in text
    assert "[there](#part)" in text
    assert not any("LEAKED" in line for line in text.splitlines() if line.startswith("#"))


def test_malformed_urls_do_not_crash_the_conversion(tmp_path: Path) -> None:
    body = '<div class="ltx_para"><p class="ltx_p"><a href="http://[x">bad</a> <img src="//[x" alt="pic"></p></div>'

    text = _md(_chapter(body, tmp_path))

    assert "bad" in text
    assert "](http" not in text
    assert "![" not in text
    assert "pic" in text


@pytest.mark.parametrize("href", ["javascript:alert(1)", "data:text/html;base64,AAAA"])
def test_unsafe_scheme_links_are_unwrapped(href: str, tmp_path: Path) -> None:
    body = f'<div class="ltx_para"><p class="ltx_p"><a href="{href}">click</a></p></div>'

    text = _md(_chapter(body, tmp_path))

    assert "click" in text
    assert "](" not in text


def test_footnote_ids_never_come_from_the_page(tmp_path: Path) -> None:
    hostile = "x) [p](https://evil"
    body = (
        f'<div class="ltx_para"><p class="ltx_p">a{NOTE.format(ident=hostile, text="first")} b'
        f"{NOTE.format(ident=hostile, text='second')} c{NOTE.format(ident='', text='third')}"
        "</p></div>"
    )

    text = _md(_chapter(body, tmp_path))

    assert "evil" not in text
    assert re.findall(r"^\[\^([^\]]+)\]: ", text, re.MULTILINE) == [
        "c0-fn-1",
        "c0-fn-2",
        "c0-fn-3",
    ]


def test_a_footnote_in_a_heading_keeps_its_text_but_not_its_marker(tmp_path: Path) -> None:
    note = NOTE.format(ident="n", text="kept note")
    body = (
        f'<section id="S1" class="ltx_section"><h4 class="ltx_title ltx_title_section">Head{note}'
        "</h4></section>"
    )

    text = _md(_chapter(body, tmp_path))

    assert "\n### Head\n" in text
    assert re.search(r"^\[\^c0-fn-1\]: kept note$", text, re.MULTILINE)


def test_math_in_a_heading_gets_no_anchor(tmp_path: Path) -> None:
    body = (
        '<section id="S1" class="ltx_section"><h4 class="ltx_title ltx_title_section">Energy '
        '<math alttext="E=mc^2" display="inline"><semantics><mi>E</mi></semantics></math></h4>'
        '<div class="ltx_para"><p class="ltx_p"><a href="#S1">up</a></p></div></section>'
    )

    text = _md(_chapter(body, tmp_path))

    assert "### Energy $E=mc^2$" in text
    assert "](#" not in text


def test_a_heading_inside_a_heading_is_rejected() -> None:
    root = lxml_html.fromstring(
        '<div><section class="ltx_chapter"><h3 class="ltx_title ltx_title_chapter">T</h3>'
        '<section class="ltx_section"><h4 class="ltx_title">A</h4></section></section></div>'
    )
    outer = root.find(".//h4")
    etree.SubElement(outer, "h5").text = "B"
    document = Document(DocumentMetadata(), (SourceChapter("t", root),))

    with pytest.raises(ReadError, match="nests a heading"):
        LatexmlFix().apply(document)


@pytest.mark.parametrize(
    ("classes", "expected"),
    [
        ("ltx_listing ltx_lst_language_C++", "```c++\n"),
        ("ltx_listing ltx_lst_language_a`b<x>", "```abx\n"),
        ("ltx_listing ltx_lst_language_Python", "```python\n"),
    ],
)
def test_listing_language_is_sanitised(classes: str, expected: str, tmp_path: Path) -> None:
    body = f'<div class="{classes}"><div class="ltx_listingline">x = 1</div></div>'

    assert expected in _md(_chapter(body, tmp_path))


@pytest.mark.parametrize("source", [" data:image/png;base64,AAAA", "//evil.example/x.png"])
def test_unsafe_image_sources_never_embed(source: str, tmp_path: Path) -> None:
    body = f'<div class="ltx_para"><p class="ltx_p"><img src="{source}" alt="pic"></p></div>'

    text = _md(_chapter(body, tmp_path))

    assert "![" not in text
    assert "evil" not in text
    assert "base64" not in text


def test_plain_text_keeps_the_text_after_comments_and_processing_instructions() -> None:
    element = lxml_html.fromstring("<p>A<!-- c --> B<?pi x?> C</p>")

    assert plain_text(element) == "A B C"


def _article() -> Document:
    document = read_html(ARTICLE)
    return replace(document, metadata=replace(document.metadata, source_file=PAPER))


def test_chapterless_paper_uses_its_sections_as_chapters() -> None:
    fixed = LatexmlFix().apply(_article())

    assert [chapter.title for chapter in fixed.chapters] == [
        "Abstract",
        "1 Introduction",
        "Acknowledgements",
        "2 Method",
        "References",
    ]
    assert fixed.metadata.title == "A Short Paper: With a Subtitle"
    assert fixed.has_math is True


def test_chapterless_paper_gets_every_other_rule() -> None:
    text = convert(_article(), extensions=["arxiv-latexml"]).body

    assert "\n### 1.1 Setup\n" in text
    assert "\n#### 1.1.1 Inputs\n" in text
    assert "We study $n$ items[^c1-fn-1]" in text
    assert "```python\nprint(1)\n```" in text
    assert "[Details](#21-details)" in text


def test_chapterless_paper_embeds_absolute_images_and_leaves_no_markup() -> None:
    text = convert(_article(), extensions=["arxiv-latexml"]).body

    assert "![Figure 1: The flow.](https://arxiv.org/html/2606.24937v3/x1.png)" in text
    assert not any(leftover in text for leftover in ("ltx_", "data:", "⬇"))


def test_a_page_with_neither_chapters_nor_sections_keeps_the_warning(tmp_path: Path) -> None:
    fixed = LatexmlFix().apply(_page("<p>plain</p>", tmp_path=tmp_path))

    assert any("LaTeXML" in warning for warning in fixed.warnings)


def _tree(count: int) -> Document:
    root = lxml_html.fromstring(
        '<div><section class="ltx_chapter"><h3 class="ltx_title ltx_title_chapter">T</h3>'
        + "<p>x</p>" * (count - 3)
        + "</section></div>"
    )
    return Document(DocumentMetadata(), (SourceChapter("t", root),))


def test_element_limit_is_inclusive() -> None:
    document = _tree(10)

    assert LatexmlFix(max_elements=10).apply(document).chapters
    with pytest.raises(ReadError, match="too many elements"):
        LatexmlFix(max_elements=9).apply(document)


def test_element_limit_is_checked_before_the_page_is_copied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copied: list[object] = []
    monkeypatch.setattr("md_studio.extractors.arxiv_latexml.deepcopy", copied.append)

    with pytest.raises(ReadError, match="too many elements"):
        LatexmlFix(max_elements=3).apply(_tree(10))

    assert not copied


def _wide(count: int) -> str:
    chapters = "".join(
        f'<section id="C{index}" class="ltx_chapter"><h3 class="ltx_title ltx_title_chapter">C{index}</h3>'
        f'<div class="ltx_para"><p class="ltx_p">t<a href="#C0">r</a></p></div></section>'
        for index in range(count)
    )
    links = "".join(f'<a href="#C{index}">l{index}</a>' for index in range(count))
    figure = (
        '<figure class="ltx_figure">'
        + "".join(f'<img src="f{index}.png" alt="Refer to caption">' for index in range(count))
        + '<figcaption class="ltx_caption">Cap</figcaption></figure>'
    )
    last = (
        '<section id="Z" class="ltx_chapter"><h3 class="ltx_title ltx_title_chapter">Z</h3>'
        f'<div class="ltx_para"><p class="ltx_p">{links}</p>{figure}</div></section>'
    )
    return f'<section id="Pt1" class="ltx_part"><h2 class="ltx_title ltx_title_part"><span class="ltx_tag ltx_tag_part">Part I </span>P</h2>{chapters}{last}</section>'


def _wide_document(count: int, tmp_path: Path) -> Document:
    document = _page(_wide(count), tmp_path=tmp_path)
    return replace(document, metadata=replace(document.metadata, source_file=PAPER))


def test_cost_stays_linear_for_many_chapters_in_one_part_many_sibling_links_and_images(
    tmp_path: Path,
) -> None:
    assert_linear(lambda size: _wide_document(size, tmp_path), 250)


@pytest.mark.parametrize(
    ("tag", "name", "rendered"),
    [
        ("h6", "theorem", "##### Thm"),
        ("h5", "acknowledgements", "#### Thm"),
        ("h4", "remark", "### Thm"),
    ],
)
def test_headings_without_a_depth_class_keep_the_tag_mapping_in_a_book(
    tag: str, name: str, rendered: str, tmp_path: Path
) -> None:
    body = (
        '<section id="S1" class="ltx_section"><h4 class="ltx_title ltx_title_section">S</h4>'
        f'<{tag} class="ltx_title ltx_title_{name}">Thm</{tag}></section>'
    )

    assert f"\n{rendered}\n" in _md(_chapter(body, tmp_path))


@pytest.mark.parametrize(
    ("tag", "rendered"),
    [("h3", "### Thm"), ("h4", "#### Thm"), ("h6", "###### Thm"), ("h2", "### Thm")],
)
def test_headings_without_a_depth_class_sit_one_level_higher_in_an_article(
    tag: str, rendered: str, tmp_path: Path
) -> None:
    body = (
        '<section id="S1" class="ltx_section"><h2 class="ltx_title ltx_title_section">S</h2>'
        f'<{tag} class="ltx_title ltx_title_theorem">Thm</{tag}></section>'
    )
    document = _page(body, tmp_path=tmp_path)

    assert f"\n{rendered}\n" in _md(document)
