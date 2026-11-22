"""Second review round: top-level title blocks, run labels, linear anchors, odd nodes everywhere."""

from dataclasses import replace
from pathlib import Path

import pytest
from lxml import etree

from md_studio.core.convert import convert
from md_studio.core.document import Document
from md_studio.extractors.arxiv_latexml import LatexmlFix
from md_studio.readers.html import read_html
from tests.extractors.linear import assert_linear
from tests.extractors.test_arxiv_latexml import FIXTURE, PAPER
from tests.extractors.test_arxiv_latexml_review import ARTICLE, _chapter, _page

TOP = Path(__file__).parents[1] / "fixtures" / "latexml_article_top.html"


def _read(path: Path) -> Document:
    document = read_html(path)
    return replace(document, metadata=replace(document.metadata, source_file=PAPER))


def test_a_top_level_title_and_authors_stay_out_of_the_abstract() -> None:
    document = _read(TOP)

    fixed = LatexmlFix().apply(document)
    text = convert(document, extensions=["arxiv-latexml"]).body

    assert fixed.metadata.title == "A Short Paper: With a Subtitle"
    assert fixed.metadata.authors == ("Ada Lovelace", "Alan Turing")
    assert [chapter.title for chapter in fixed.chapters] == ["Abstract", "1 Introduction"]
    abstract = text.split("## 1 Introduction")[0]
    assert "Only the abstract." in abstract
    assert not any(stray in abstract for stray in ("Ada", "Turing", "Subtitle", "Short Paper"))


def test_a_run_before_the_first_section_is_front_matter_and_later_runs_are_additional(
    tmp_path: Path,
) -> None:
    body = (
        '<div class="ltx_para"><p class="ltx_p">Before.</p></div>'
        '<section id="S1" class="ltx_section"><h2 class="ltx_title ltx_title_section">One</h2>'
        '<div class="ltx_para"><p class="ltx_p">In.</p></div></section>'
        '<div class="ltx_para"><p class="ltx_p">After.</p></div>'
    )
    document = _page(body, tmp_path=tmp_path)

    fixed = LatexmlFix().apply(document)

    assert [chapter.title for chapter in fixed.chapters] == [
        "Front matter",
        "One",
        "Additional material",
    ]


def _heading_last(count: int, tmp_path: Path) -> Document:
    children = "".join(
        f'<div id="d{index}" class="ltx_para"><p class="ltx_p">t</p></div>'
        for index in range(count)
    )
    body = (
        f'<section id="S1" class="ltx_section">{children}'
        '<h4 class="ltx_title ltx_title_section">Last</h4></section>'
    )
    return _chapter(body, tmp_path)


def _headingless(count: int, tmp_path: Path) -> Document:
    nested = "".join(
        f'<section id="n{index}" class="ltx_subsection"><div id="m{index}" class="ltx_para">'
        '<p class="ltx_p">x</p></div></section>'
        for index in range(count // 4)
    )
    children = "".join(
        f'<div id="d{index}" class="ltx_para"><p class="ltx_p">t</p></div>'
        for index in range(count)
    )
    return _chapter(f'<section id="S1" class="ltx_section">{children}{nested}</section>', tmp_path)


def test_anchors_stay_linear_when_a_section_heading_comes_last(tmp_path: Path) -> None:
    assert_linear(lambda size: _heading_last(size, tmp_path), 250)


def test_anchors_stay_linear_for_sections_with_no_heading_at_all(tmp_path: Path) -> None:
    assert_linear(lambda size: _headingless(size, tmp_path), 250)


RUNS = 7


def _insert_noise(document: Document, run: int) -> None:
    """Add a comment and a processing instruction inside and after every element of one run."""
    root = document.chapters[0].element
    elements = [node for node in root.iter() if isinstance(node.tag, str)]
    for index, node in enumerate(elements):
        if index % RUNS != run:
            continue
        node.insert(0, etree.Comment(" c "))
        node.append(etree.ProcessingInstruction("pi", "x"))
        if node is not root:
            node.addnext(etree.ProcessingInstruction("after", "y"))
            node.addnext(etree.Comment(" t "))


@pytest.mark.parametrize("fixture", [FIXTURE, ARTICLE, TOP], ids=["mini", "article", "top"])
@pytest.mark.parametrize("run", range(RUNS))
def test_comments_and_instructions_change_nothing_anywhere(fixture: Path, run: int) -> None:
    clean = convert(_read(fixture), extensions=["arxiv-latexml"]).text
    noisy_document = _read(fixture)
    _insert_noise(noisy_document, run)

    noisy = convert(noisy_document, extensions=["arxiv-latexml"]).text

    assert noisy == clean
