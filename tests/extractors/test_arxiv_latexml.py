"""The LaTeXML source fix, on a small hand-built page that mirrors arXiv's markup."""

import re
from dataclasses import replace
from importlib.metadata import entry_points
from pathlib import Path
from typing import cast

import pytest
from lxml import html

from md_studio.core.convert import convert
from md_studio.core.document import Document
from md_studio.core.exceptions import ReadError, UnknownExtensionError
from md_studio.core.extensions import discover, resolve
from md_studio.core.extensions import discovery as discovery_mod
from md_studio.extractors.arxiv_latexml import LatexmlFix
from md_studio.extractors.latexml_slugs import github_slugs, slugify
from md_studio.readers.html import read_html
from tests.extractors.linear import assert_linear

FIXTURE = Path(__file__).parents[1] / "fixtures" / "latexml_mini.html"
PAPER = "https://arxiv.org/html/2606.24937v3"
SOFTMAX_BLOCK = r"""$$
\text{softmax}(z)_{i}=\frac{e^{z_{i}}}{\sum_{j}e^{z_{j}}}
$$"""
ALIGNED_BLOCK = r"""$$
\begin{aligned}
\displaystyle h(x) & \displaystyle=W_{g}\cdot x \\
\displaystyle H(x) & \displaystyle=h(x)+b
\end{aligned}
$$"""
ABSOLUTE_FIGURE = "https://arxiv.org/html/2606.24937v3/figures/fig1.png"


def _document(source: str = PAPER) -> Document:
    loaded = read_html(FIXTURE)
    return replace(loaded, metadata=replace(loaded.metadata, source_file=source))


def _fixed(source: str = PAPER) -> Document:
    return LatexmlFix().apply(_document(source))


def _markdown(source: str = PAPER) -> str:
    return convert(_document(source), extensions=["arxiv-latexml"]).body


def _page(body: str, name: str = "page.html", tmp_path: Path | None = None) -> Document:
    assert tmp_path is not None
    path = tmp_path / name
    path.write_text(f"<html><head><title>T</title></head><body>{body}</body></html>")
    return read_html(path)


def _titles(document: Document) -> list[str]:
    return [chapter.title for chapter in document.chapters]


def test_fix_is_registered_under_the_name_the_extractor_plans() -> None:
    assert discover()["arxiv-latexml"] is LatexmlFix


def test_fix_is_registered_through_the_entry_point_group() -> None:
    registered = {
        entry.name: entry.value for entry in entry_points(group=discovery_mod.ENTRY_POINT_GROUP)
    }

    assert registered["arxiv-latexml"] == "md_studio.extractors.arxiv_latexml:LatexmlFix"


def test_without_the_entry_point_the_fix_is_reported_unregistered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: [])

    with pytest.raises(UnknownExtensionError, match="arxiv-latexml"):
        resolve(["arxiv-latexml"])


def test_chapters_include_appendix_and_bibliography() -> None:
    titles = _titles(_fixed())

    assert len(titles) == 7
    assert titles[0] == "Disclaimer"
    assert titles[-2:] == ["References", "Appendix A Background"]


def test_part_prefix_in_titles() -> None:
    titles = _titles(_fixed())

    assert titles[2:5] == [
        "Part I · Chapter 1 Basics",
        "Part I · Chapter 2 Systems",
        "Part II · Chapter 3 Wrap up",
    ]
    assert not any(title.startswith("Part") for title in titles[:2] + titles[5:])


def test_navigation_toc_is_skipped() -> None:
    text = _markdown()

    assert "Contents" not in text
    assert text.count("Disclaimer") == 1


def test_headings_demoted() -> None:
    text = _markdown()

    wanted = (
        "\n## Part I · Chapter 1 Basics\n",
        "\n### 1.1 Softmax\n",
        "\n#### 1.1.1 Temperature\n",
        "\n##### Scaling\n",
        "\n**Lead in.**\n",
    )
    assert all(heading in text for heading in wanted)
    assert "\n# " not in text


def test_chapters_own_title_is_not_repeated() -> None:
    assert _markdown().count("Chapter 1 Basics") == 1


def test_listing_becomes_fenced_code_with_language() -> None:
    text = _markdown()

    assert "```python\ndef f():\n    return 1\n```" in text
    assert "⬇" not in text


def test_footnotes_rewritten() -> None:
    text = _markdown()

    assert re.search(r"Provided as is\[\^c0-fn-1\]", text)
    assert re.search(r"^\[\^c0-fn-1\]: .*https://example\.org/terms", text, re.MULTILINE)
    assert re.search(r"^\[\^c3-fn-2\]: A second note\.$", text, re.MULTILINE)
    assert len(re.findall(r"^\[\^[^\]]+\]: ", text, re.MULTILINE)) == 2


def test_images_absolute_and_caption_alt() -> None:
    text = _markdown()

    assert f"![Figure 1.1: A diagram of k steps.]({ABSOLUTE_FIGURE})" in text
    assert "Refer to caption" not in text
    assert "base64" not in text
    assert "Inline logo." in text


def _single(body: str, source: str, tmp_path: Path) -> Document:
    wrapped = (
        '<section id="Ch1" class="ltx_chapter"><h3 class="ltx_title ltx_title_chapter">One</h3>'
        f'<div class="ltx_para"><p class="ltx_p">text</p>{body}</div></section>'
    )
    loaded = _page(wrapped, tmp_path=tmp_path)
    return replace(loaded, metadata=replace(loaded.metadata, source_file=source))


def test_bare_image_names_resolve_against_the_paper_named_by_the_source(tmp_path: Path) -> None:
    document = _single('<img src="x1.png" alt="Refer to caption">', PAPER, tmp_path)

    text = convert(document, extensions=["arxiv-latexml"]).body

    assert "![image](https://arxiv.org/html/2606.24937v3/x1.png)" in text


def test_equation_table_becomes_math_block_not_a_table() -> None:
    text = _markdown()

    assert SOFTMAX_BLOCK in text
    assert not any(leftover in text for leftover in ("(1.1)", "|  |"))


def test_equation_group_becomes_math_block() -> None:
    text = _markdown()

    assert ALIGNED_BLOCK in text
    assert "(clean)" not in text


def test_inline_math_comes_from_alttext_and_passes_through_unchanged() -> None:
    text = _markdown()

    assert r"Intro with $k$ and cost $\$5$." in text


def test_list_item_labels_are_dropped() -> None:
    text = _markdown()

    assert "- First point\n- Second point" in text
    assert "•" not in text


def test_document_has_math() -> None:
    assert _fixed().has_math is True


def test_document_without_math_stays_math_free(tmp_path: Path) -> None:
    document = _single("", PAPER, tmp_path)

    assert LatexmlFix().apply(document).has_math is False


def test_data_table_is_still_a_table() -> None:
    text = _markdown()

    assert "| Agent | Role |" in text
    assert "| Supervisor | Orchestrates the rest. |" in text


def test_cross_chapter_refs_resolve() -> None:
    text = _markdown()

    links = (
        "[Chapter 1](#part-i--chapter-1-basics)",
        "[Section 2.1](#21-basics)",
        "[Section 1.1](#11-softmax)",
    )
    assert all(link in text for link in links)
    assert not any(dead in text for dead in ("(#bib.bib1)", "(#nowhere)"))
    assert "missing target" in text


def test_every_internal_link_points_at_an_output_heading() -> None:
    text = _markdown()
    headings = {slugify(line.lstrip("# ")) for line in text.splitlines() if line.startswith("##")}

    targets = re.findall(r"\]\(#([^)]+)\)", text)

    assert targets
    assert set(targets) <= headings


def test_repeated_headings_get_numbered_slugs() -> None:
    assert github_slugs(["Intro", "Intro", "Intro", "Other"]) == [
        "intro",
        "intro-1",
        "intro-2",
        "other",
    ]


def test_no_ltx_or_data_uri_remains() -> None:
    text = _markdown()

    for leftover in ("ltx_", "data:", "⬇", "Refer to caption", "base64"):
        assert leftover not in text


def test_title_is_built_from_the_title_page_not_the_glued_title_element() -> None:
    assert _fixed().metadata.title == "The Mini Guide: From Basics to Systems"


def test_input_document_is_not_mutated() -> None:
    document = _document()
    before = html.tostring(cast(html.HtmlElement, document.chapters[0].element))

    LatexmlFix().apply(document)

    assert html.tostring(cast(html.HtmlElement, document.chapters[0].element)) == before


def test_page_without_latexml_structure_is_returned_unchanged_with_a_warning(
    tmp_path: Path,
) -> None:
    document = _page("<p>plain</p>", tmp_path=tmp_path)

    fixed = LatexmlFix().apply(document)

    assert fixed.chapters == document.chapters
    assert any("LaTeXML" in warning for warning in fixed.warnings)


def test_relative_image_stays_relative_and_warns_when_the_paper_is_unknown(
    tmp_path: Path,
) -> None:
    document = _single('<img src="x1.png" alt="Refer to caption">', "page.html", tmp_path)

    fixed = LatexmlFix().apply(document)

    assert any("image" in warning for warning in fixed.warnings)
    assert "https://" not in convert(fixed).body


def test_nested_chapters_are_not_duplicated(tmp_path: Path) -> None:
    body = (
        '<section id="Ch1" class="ltx_chapter"><h3 class="ltx_title ltx_title_chapter">A</h3>'
        '<section id="Ch2" class="ltx_chapter"><h3 class="ltx_title ltx_title_chapter">B</h3>'
        "<div><p>inner</p></div></section></section>"
    )

    fixed = LatexmlFix().apply(_page(body, tmp_path=tmp_path))

    assert _titles(fixed) == ["A"]


def test_element_cap_rejects_an_oversized_page() -> None:
    with pytest.raises(ReadError, match="too many elements"):
        LatexmlFix(max_elements=50).apply(_document())


def _synthetic(chapters: int, sections: int) -> str:
    section = (
        '<section id="{c}.S{s}" class="ltx_section">'
        '<h4 class="ltx_title ltx_title_section"><span class="ltx_tag">{s} </span>Title {s}</h4>'
        '<div class="ltx_para"><p class="ltx_p">Text <math alttext="x_{{{s}}}" display="inline">'
        "<semantics><mi>x</mi></semantics></math> and a note"
        '<span id="{c}.footnote{s}" class="ltx_note ltx_role_footnote"><sup class="ltx_note_mark">'
        '1</sup><span class="ltx_note_outer"><span class="ltx_note_content">N{s}</span></span>'
        '</span> see <a href="#{c}.S0" class="ltx_ref">ref</a>.</p></div>'
        '<table class="ltx_equation ltx_eqn_table"><tbody><tr class="ltx_eqn_row"><td>'
        '<math alttext="a={s}" display="block"><semantics><mi>a</mi></semantics></math>'
        "</td></tr></tbody></table>"
        '<div class="ltx_listing ltx_lst_language_Python"><div class="ltx_listingline">'
        "x = {s}</div></div>"
        '<figure class="ltx_figure"><img src="f{s}.png" alt="Refer to caption">'
        '<figcaption class="ltx_caption">Cap {s}</figcaption></figure></section>'
    )
    chapter = (
        '<section id="{c}" class="ltx_chapter"><h3 class="ltx_title ltx_title_chapter">'
        "Chapter {c}</h3>{body}</section>"
    )
    return "".join(
        chapter.format(
            c=f"Ch{number}",
            body="".join(section.format(c=f"Ch{number}", s=index + 1) for index in range(sections)),
        )
        for number in range(chapters)
    )


def _synthetic_document(chapters: int, sections: int, tmp_path: Path) -> Document:
    document = _page(_synthetic(chapters, sections), tmp_path=tmp_path)
    return replace(document, metadata=replace(document.metadata, source_file=PAPER))


def test_cost_grows_linearly_with_the_sections_of_one_chapter(tmp_path: Path) -> None:
    assert_linear(lambda size: _synthetic_document(1, size, tmp_path), 80)


def test_cost_grows_linearly_with_the_number_of_chapters(tmp_path: Path) -> None:
    assert_linear(lambda size: _synthetic_document(size, 5, tmp_path), 20)
