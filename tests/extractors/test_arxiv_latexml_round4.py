"""Fourth review round: links that wrap hoisted constructs are rewritten in every clone."""

from pathlib import Path

from tests.extractors.test_arxiv_latexml_review import _chapter, _md
from tests.extractors.test_arxiv_latexml_round3 import EQUATION, LISTING


def _text(inner: str, tmp_path: Path) -> str:
    body = (
        '<section id="S1" class="ltx_section"><h4 class="ltx_title ltx_title_section">Results'
        f'</h4><div class="ltx_para"><p class="ltx_p">{inner}</p></div></section>'
    )
    return _md(_chapter(body, tmp_path))


def test_both_clones_of_a_link_around_a_listing_point_at_the_emitted_anchor(
    tmp_path: Path,
) -> None:
    inner = f'<a href="#S1">before{LISTING.format(code="x")}after</a>'

    text = _text(inner, tmp_path)

    assert "[before](#results)" in text
    assert "[after](#results)" in text
    assert "#S1" not in text


def test_a_link_around_two_constructs_is_rewritten_in_all_three_clones(tmp_path: Path) -> None:
    inner = f'<a href="#S1">a{LISTING.format(code="x")}b{EQUATION.format(tex="y")}c</a>'

    text = _text(inner, tmp_path)

    assert text.count("(#results)") == 3
    assert "#S1" not in text


def test_a_nested_link_in_a_wrapper_chain_is_rewritten_in_both_clones(tmp_path: Path) -> None:
    inner = f'<em>x <a href="#S1">p{LISTING.format(code="x")}q</a> y</em>'

    text = _text(inner, tmp_path)

    assert text.count("(#results)") == 2
    assert "#S1" not in text


def test_an_external_link_is_kept_in_both_clones(tmp_path: Path) -> None:
    inner = f'<a href="https://example.org/a">left{LISTING.format(code="x")}right</a>'

    text = _text(inner, tmp_path)

    assert "[left](https://example.org/a)" in text
    assert "[right](https://example.org/a)" in text


def test_a_dead_link_is_unwrapped_in_both_clones(tmp_path: Path) -> None:
    inner = f'<a href="#nowhere">left{LISTING.format(code="x")}right</a>'

    text = _text(inner, tmp_path)

    assert "nowhere" not in text
    assert "](" not in text
    assert "left" in text
    assert "right" in text
