"""PR review fixes: article front matter, reading order, slug numbering, odd nodes, URLs."""

import re
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from lxml import etree
from lxml import html as lxml_html

from md_studio.core.convert import convert
from md_studio.core.document import Document
from md_studio.extractors.arxiv_latexml import LatexmlFix
from md_studio.readers.html import read_html
from tests.extractors.test_arxiv_latexml import PAPER, _markdown
from tests.extractors.test_arxiv_latexml_review import _article, _chapter, _md

MARK = "\u2063"
DROPPED_CLASSES = frozenset((
    "ltx_titlepage",
    "ltx_TOC",
    "ltx_listing_data",
    "ltx_note_mark",
    "ltx_tag_note",
    "ltx_pagination",
))


def _collapse(text: str) -> str:
    return " ".join(text.split())


def test_article_keeps_abstract_keywords_and_acknowledgements() -> None:
    fixed = LatexmlFix().apply(_article())

    assert [chapter.title for chapter in fixed.chapters] == [
        "Abstract",
        "1 Introduction",
        "Acknowledgements",
        "2 Method",
        "References",
    ]


def test_article_front_matter_renders_under_its_own_headings_in_order() -> None:
    text = convert(_article(), extensions=["arxiv-latexml"]).body

    order = [
        text.index("## Abstract\n"),
        text.index("We show that the method works."),
        text.index("Keywords: agents, memory"),
        text.index("\n## 1 Introduction\n"),
        text.index("\n## Acknowledgements\n"),
        text.index("Thanks to the reviewers."),
        text.index("\n## 2 Method\n"),
    ]
    assert order == sorted(order)
    assert text.count("Abstract") == 1
    assert text.count("Acknowledgements") == 1


def _skipped(element: lxml_html.HtmlElement) -> bool:
    classes = set(element.get("class", "").split())
    return bool(classes & DROPPED_CLASSES) or element.tag in {"math", "title"}


def _visible_text(root: lxml_html.HtmlElement) -> list[str]:
    copy = deepcopy(root)
    skipped = [found for found in copy.iter() if isinstance(found.tag, str) and _skipped(found)]
    for node in skipped:
        _blank(node)
    return [_collapse(text) for text in copy.itertext() if text.strip() and text != MARK]


def _blank(node: lxml_html.HtmlElement) -> None:
    """Replace a node that the output rewrites by a mark, keeping the text that follows it."""
    tail = node.tail
    node.clear()
    node.text = MARK
    node.tail = tail


def test_no_visible_source_text_is_lost_in_an_article() -> None:
    document = _article()
    source = _visible_text(document.chapters[0].element)
    output = _collapse(convert(document, extensions=["arxiv-latexml"]).body)

    missing = [chunk for chunk in source if chunk not in output]

    assert source
    assert not missing


def test_hoisted_blocks_split_the_paragraph_and_keep_reading_order() -> None:
    text = _markdown()

    assert "Inline code\n\n```c++\nint x;\n```\n\nends." in text
    assert "Then\n\n$$\ny=2\n$$\n\nand\n\n$$\nz=3\n$$\n\ndone." in text


def test_splitting_a_paragraph_with_many_blocks_keeps_every_segment(tmp_path: Path) -> None:
    pieces = "".join(
        f'w{index} <span class="ltx_equation ltx_eqn_table"><span class="ltx_eqn_row">'
        f'<math alttext="e{index}" display="block"></math></span></span> '
        for index in range(5)
    )
    body = f'<div class="ltx_para"><p class="ltx_p">{pieces}end</p></div>'

    text = _md(_chapter(body, tmp_path))

    expected = "\n\n".join(f"w{index}\n\n$$\ne{index}\n$$" for index in range(5))
    assert f"{expected}\n\nend" in text


def test_repeated_heading_text_is_numbered_across_all_rendered_headings(tmp_path: Path) -> None:
    body = (
        '<h5 class="ltx_title ltx_title_theorem">Details</h5>'
        '<section id="S1" class="ltx_section"><h4 class="ltx_title ltx_title_section">Details</h4>'
        '<div class="ltx_para"><p class="ltx_p"><a href="#S1">here</a></p></div></section>'
    )

    text = _md(_chapter(body, tmp_path))

    assert "[here](#details-1)" in text


def _sprinkle(document: Document) -> Document:
    root = document.chapters[0].element
    for element in list(root.iter()):
        if isinstance(element.tag, str) and element.get("data-n"):
            element.insert(0, etree.Comment("LEAKC"))
            element.append(etree.ProcessingInstruction("leakp", "x"))
    return document


NOISY = (
    '<section id="Pt" class="ltx_part"><h2 data-n="1" class="ltx_title ltx_title_part">'
    '<span class="ltx_tag ltx_tag_part">Part I </span>Foundations</h2>'
    '<section id="Ch1" class="ltx_chapter"><h3 class="ltx_title ltx_title_chapter">One</h3>'
    '<div class="ltx_para"><p class="ltx_p">Text<span id="n" class="ltx_note ltx_role_footnote">'
    '<sup class="ltx_note_mark">1</sup><span class="ltx_note_outer">'
    '<span data-n="1" class="ltx_note_content">kept note</span></span></span> end.</p></div>'
    '<div data-n="1" class="ltx_listing ltx_lst_language_Python">'
    '<div class="ltx_listingline">x = 1</div></div>'
    '<figure data-n="1" class="ltx_figure"><img src="2606.24937v3/a.png" alt="Refer to caption">'
    '<figcaption class="ltx_caption">A caption.</figcaption></figure>'
    '<table data-n="1" class="ltx_tabular"><tbody><tr data-n="1"><td>cell</td></tr></tbody></table>'
    "</section></section>"
)


def _noisy(tmp_path: Path) -> Document:
    path = tmp_path / "noisy.html"
    path.write_text(f"<html><head><title>T</title></head><body>{NOISY}</body></html>")
    document = read_html(path)
    return _sprinkle(replace(document, metadata=replace(document.metadata, source_file=PAPER)))


def test_comments_and_processing_instructions_do_not_crash_or_leak(tmp_path: Path) -> None:
    text = convert(_noisy(tmp_path), extensions=["arxiv-latexml"]).text

    assert not any(leak in text for leak in ("LEAKC", "leakp"))
    expected = ("## Part I · One", "kept note", "x = 1", "A caption.", "cell")
    assert all(wanted in text for wanted in expected)


def test_protocol_relative_links_are_unwrapped(tmp_path: Path) -> None:
    body = '<div class="ltx_para"><p class="ltx_p"><a href="//evil.example/x">go</a></p></div>'

    text = _md(_chapter(body, tmp_path))

    assert "go" in text
    assert "evil" not in text


def test_an_unresolvable_relative_link_is_reported(tmp_path: Path) -> None:
    body = '<div class="ltx_para"><p class="ltx_p"><a href="sub/page.html">go</a></p></div>'
    page = _chapter(body, tmp_path)
    document = replace(page, metadata=replace(page.metadata, source_file="x.html"))

    fixed = LatexmlFix().apply(document)

    assert any("link" in warning for warning in fixed.warnings)


def test_a_relative_link_resolves_when_the_paper_is_known(tmp_path: Path) -> None:
    body = '<div class="ltx_para"><p class="ltx_p"><a href="sub/page.html">go</a></p></div>'

    fixed = LatexmlFix().apply(_chapter(body, tmp_path))

    assert not any("link" in warning for warning in fixed.warnings)
    assert "(https://arxiv.org/html/2606.24937v3/sub/page.html)" in _md(_chapter(body, tmp_path))


def test_a_footnote_in_a_caption_does_not_leak_its_number_into_the_alt_text(tmp_path: Path) -> None:
    note = (
        '<span id="n" class="ltx_note ltx_role_footnote"><sup class="ltx_note_mark">1</sup>'
        '<span class="ltx_note_outer"><span class="ltx_note_content">aside</span></span></span>'
    )
    body = (
        '<figure class="ltx_figure"><img src="2606.24937v3/a.png" alt="Refer to caption">'
        f'<figcaption class="ltx_caption">Flow{note} chart.</figcaption></figure>'
    )

    text = _md(_chapter(body, tmp_path))

    assert "![Flow chart.](https://arxiv.org/html/2606.24937v3/a.png)" in text


@pytest.mark.parametrize(
    "source",
    [
        "file:///etc/passwd",
        "ftp://example.org/x.png",
        "vbscript:msgbox(1)",
        "data:image/png;base64,AAAA",
        "//evil.example/x.png",
    ],
)
def test_only_http_sources_survive_the_fix_layer(source: str, tmp_path: Path) -> None:
    body = f'<div class="ltx_para"><p class="ltx_p"><img src="{source}" alt="pic"></p></div>'
    document = _chapter(body, tmp_path)

    fixed = LatexmlFix().apply(document)
    images = [
        image
        for chapter in fixed.chapters
        for image in chapter.element.iter("img")  # type: ignore[attr-defined]
    ]

    assert all(image.get("src", "") == "" for image in images)
    text = convert(document, extensions=["arxiv-latexml"]).body
    assert "![" not in text
    assert not re.search(r"file:|ftp:|vbscript|evil", text)
