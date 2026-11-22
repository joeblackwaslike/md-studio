"""Third review round: nested splits, headingless anchors, math titles, missing TeX, timings."""

from functools import partial
from pathlib import Path

from md_studio.core.convert import convert
from md_studio.core.document import Document
from md_studio.extractors.arxiv_latexml import LatexmlFix
from tests.extractors.linear import assert_linear
from tests.extractors.test_arxiv_latexml_review import _chapter, _md

LISTING = (
    '<span class="ltx_listing ltx_lst_language_Python">'
    '<span class="ltx_listingline">{code}</span></span>'
)
EQUATION = (
    '<span class="ltx_equation ltx_eqn_table"><span class="ltx_eqn_row">'
    '<math alttext="{tex}" display="block"></math></span></span>'
)


def _paragraph(inner: str, tmp_path: Path) -> str:
    return _md(_chapter(f'<div class="ltx_para"><p class="ltx_p">{inner}</p></div>', tmp_path))


def _fence(code: str) -> str:
    return f"```python\n{code}\n```"


def test_a_listing_inside_a_strong_wrapper_splits_the_wrapper(tmp_path: Path) -> None:
    inner = f"A<strong>B{LISTING.format(code='x')}C</strong>D"

    text = _paragraph(inner, tmp_path)

    assert f"A**B**\n\n{_fence('x')}\n\n**C**D" in text


def test_a_listing_inside_an_emphasis_wrapper_keeps_the_text_after_it(tmp_path: Path) -> None:
    inner = f"<em>before {LISTING.format(code='x')} after</em> end"

    text = _paragraph(inner, tmp_path)

    assert f"*before*\n\n{_fence('x')}\n\n*after* end" in text


def test_an_equation_inside_a_wrapper_splits_it(tmp_path: Path) -> None:
    inner = f"A<strong>B{EQUATION.format(tex='e=1')}C</strong>D"

    text = _paragraph(inner, tmp_path)

    assert "A**B**\n\n$$\ne=1\n$$\n\n**C**D" in text


def test_two_constructs_in_one_wrapper_keep_their_interleaving(tmp_path: Path) -> None:
    inner = f"<em>a {LISTING.format(code='x')} b {EQUATION.format(tex='y')} c</em> d"

    text = _paragraph(inner, tmp_path)

    expected = f"*a*\n\n{_fence('x')}\n\n*b*\n\n$$\ny\n$$\n\n*c* d"
    assert expected in text


def test_a_wrapper_inside_a_wrapper_is_reopened_in_full(tmp_path: Path) -> None:
    inner = f"<strong>1<em>2 {LISTING.format(code='x')} 3</em>4</strong>5"

    text = _paragraph(inner, tmp_path)

    assert f"**1*2***\n\n{_fence('x')}\n\n***3*4**5" in text


def test_a_wrapper_with_nothing_after_the_construct_leaves_no_empty_markup(tmp_path: Path) -> None:
    inner = f"A<strong>B{LISTING.format(code='x')}</strong>"

    text = _paragraph(inner, tmp_path)

    assert f"A**B**\n\n{_fence('x')}\n" in text
    assert "****" not in text


def test_reopened_wrappers_do_not_repeat_ids(tmp_path: Path) -> None:
    inner = f'<span id="w" class="ltx_text">a {LISTING.format(code="x")} b</span>'
    document = _chapter(f'<div class="ltx_para"><p class="ltx_p">{inner}</p></div>', tmp_path)

    fixed = LatexmlFix().apply(document)
    ids = [node.get("id") for node in fixed.chapters[0].element.iter() if node.get("id") == "w"]  # type: ignore[attr-defined]

    assert len(ids) <= 1


def _many_document(count: int, tmp_path: Path) -> Document:
    inner = "".join(
        f"<em>t{index} {LISTING.format(code=f'c{index}')} u{index}</em> " for index in range(count)
    )
    return _chapter(f'<div class="ltx_para"><p class="ltx_p">{inner}end</p></div>', tmp_path)


def test_cost_stays_linear_with_many_nested_constructs(tmp_path: Path) -> None:
    assert_linear(partial(_many_document, tmp_path=tmp_path), 60)


def _interleaved(text: str, count: int) -> list[int]:
    """Positions of t0, u0, t1, u1 ... in *text*, which must be increasing."""
    names = [f"*{prefix}{index}*" for index in range(count) for prefix in "tu"]
    return [text.index(name) for name in names]


def test_the_many_construct_paragraph_keeps_every_segment_in_order(tmp_path: Path) -> None:
    text = convert(_many_document(30, tmp_path), extensions=["arxiv-latexml"]).body

    positions = _interleaved(text, 30)

    assert positions == sorted(positions)


MATH = '<math alttext="{tex}" display="inline"><semantics><mi>e</mi></semantics></math>'
BARE = '<math display="{display}"><semantics><mi>{text}</mi></semantics></math>'
EPSILON = r"\epsilon"
EQUATION_ROW = (
    '<table class="ltx_equation ltx_eqn_table"><tbody><tr class="ltx_eqn_row"><td>'
    "{math}</td></tr></tbody></table>"
)
SECTION = (
    '<section id="S1" class="ltx_section"><h4 class="ltx_title ltx_title_section">{title}</h4>'
    "{rest}</section>"
)


def _bare(display: str, text: str) -> str:
    return BARE.format(display=display, text=text)


def test_a_chapter_title_keeps_its_math_delimiters(tmp_path: Path) -> None:
    title = f"Bounds on {MATH.format(tex=EPSILON)}"

    text = _md(_chapter("", tmp_path, title=title))

    assert text.startswith(f"## Bounds on ${EPSILON}$\n")


def test_a_section_title_keeps_its_math_delimiters(tmp_path: Path) -> None:
    body = SECTION.format(title=f"Bounds on {MATH.format(tex=EPSILON)}", rest="")

    assert f"\n### Bounds on ${EPSILON}$\n" in _md(_chapter(body, tmp_path))


def test_math_titles_and_anchors_stay_consistent(tmp_path: Path) -> None:
    link = '<div class="ltx_para"><p class="ltx_p"><a href="#S1">there</a></p></div>'
    body = SECTION.format(title="Bounds on epsilon!", rest=link)
    title = f"Bounds on {MATH.format(tex='epsilon')}"

    text = _md(_chapter(body, tmp_path, title=title))

    assert text.startswith("## Bounds on $epsilon$\n")
    assert "[there](#bounds-on-epsilon-1)" in text


def _tex_notes(body: str, tmp_path: Path) -> list[str]:
    warnings = LatexmlFix().apply(_chapter(body, tmp_path)).warnings
    return [warning for warning in warnings if "TeX source" in warning]


def test_inline_math_without_tex_falls_back_to_its_text_and_warns(tmp_path: Path) -> None:
    body = f'<div class="ltx_para"><p class="ltx_p">a {_bare("inline", "x2")} b</p></div>'

    assert "a $x2$ b" in _md(_chapter(body, tmp_path))
    assert _tex_notes(body, tmp_path) == [
        "arxiv-latexml: 1 math elements had no TeX source; used their text content"
    ]


def test_display_math_without_tex_falls_back_to_its_text(tmp_path: Path) -> None:
    body = f'<div class="ltx_para">{_bare("block", "E=mc2")}</div>'

    assert "$$\nE=mc2\n$$" in _md(_chapter(body, tmp_path))


def test_an_equation_table_without_tex_falls_back_to_its_text(tmp_path: Path) -> None:
    body = EQUATION_ROW.format(math=_bare("block", "z=1"))

    assert "$$\nz=1\n$$" in _md(_chapter(body, tmp_path))


def test_missing_tex_is_counted_once_across_every_kind(tmp_path: Path) -> None:
    inline = " ".join(_bare("inline", text) for text in ("a", "b", ""))
    body = (
        f'<div class="ltx_para"><p class="ltx_p">{inline}</p>'
        f"{EQUATION_ROW.format(math=_bare('block', 'z=1'))}</div>"
    )

    assert _tex_notes(body, tmp_path) == [
        "arxiv-latexml: 4 math elements had no TeX source; used their text content"
    ]


def test_math_with_tex_adds_no_warning(tmp_path: Path) -> None:
    body = f'<div class="ltx_para"><p class="ltx_p">{MATH.format(tex="x")}</p></div>'

    assert not _tex_notes(body, tmp_path)
