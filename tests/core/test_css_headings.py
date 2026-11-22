"""CSS heading classifier, audit records, and the fix-headings integration."""

import socket
from pathlib import Path

import pytest

from md_studio.core.convert import convert
from md_studio.core.extensions import audit, css_classes, css_headings
from md_studio.readers.epub import read_epub
from tests.readers._epub import (
    CSS_HEADINGS_STYLESHEET,
    ChapterSpec,
    build_css_headings_epub,
    build_epub,
)

_HOSTILE = (
    "",
    "}{",
    ".a{",
    "\x00\x00\x00",
    "@media{{{{",
    ".a{font-size:1e999rem}",
    ".a{font-size:99999999999999999999999999rem;font-weight:bold}",
    ".a{font-size:-3rem}.b{font-size:rem}.c{font-size:1.2.3rem}",
    f"{', '.join(f'.c{index}' for index in range(60_000))}{{font-size:2rem}}",
    "{" * 50_000,
)


def test_classify_ranks_classes_by_size() -> None:
    assert css_headings.classify(CSS_HEADINGS_STYLESHEET) == {
        "class-part": 1,
        "class-section": 2,
        "class-sub": 3,
    }


def test_classify_groups_sizes_within_a_tenth_of_a_rem() -> None:
    sheet = ".a{font-size:2rem}.b{font-size:1.95rem}.c{font-size:1.5rem}"

    assert css_headings.classify(sheet) == {"a": 1, "b": 1, "c": 2}


def test_classify_caps_levels_at_six() -> None:
    sheet = "".join(f".c{index}{{font-size:{3 - index * 0.2}rem}}" for index in range(8))

    assert max(css_headings.classify(sheet).values()) == 6


def test_classify_ignores_small_plain_text() -> None:
    assert (
        css_headings.classify(".body{font-size:1rem}.bold{font-size:1rem;font-weight:bold}") == {}
    )


@pytest.mark.parametrize("stylesheet", _HOSTILE)
def test_classify_survives_hostile_css(stylesheet: str) -> None:
    assert css_headings.classify(stylesheet) == {}


def _refuse_network(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("network access attempted")


def test_classify_never_fetches_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", _refuse_network)
    sheet = '@import url("http://127.0.0.1:9/x.css");@import "http://127.0.0.1:9/y.css";.a{font-size:2rem}'

    assert css_headings.classify(sheet) == {"a": 1}


def _markdown(tmp_path: Path, *names: str) -> str:
    document = read_epub(build_css_headings_epub(tmp_path / "styled.epub"))
    return convert(document, extensions=list(names)).text


def test_css_styled_div_promoted_to_heading_level(tmp_path: Path) -> None:
    text = _markdown(tmp_path, "fix-headings")

    assert "\n## Part One\n" in text
    assert "\n### Section A\n" in text
    assert "\n#### Sub A1\n" in text
    assert "\nPlain body text.\n" in text


def test_default_conversion_leaves_css_headings_as_paragraphs(tmp_path: Path) -> None:
    document = read_epub(build_css_headings_epub(tmp_path / "styled.epub"))

    rendered = convert(document)

    assert "\nPart One\n" in rendered.text
    assert rendered.promotions == ()


def test_audit_lists_every_promotion(tmp_path: Path) -> None:
    document = read_epub(build_css_headings_epub(tmp_path / "styled.epub"))

    rendered = convert(document, extensions=["fix-headings"])

    assert rendered.promotions == (
        audit.PromotionRecord("Chapter One", "Part One", "div", ("class-part",), 1),
        audit.PromotionRecord("Chapter One", "Section A", "div", ("class-section",), 2),
        audit.PromotionRecord("Chapter One", "Sub A1", "div", ("class-sub",), 3),
    )
    report = audit.render(rendered.promotions)
    assert all(record.text in report for record in rendered.promotions)
    assert report.count("class-") == 3


@pytest.mark.parametrize(
    ("text", "cell"),
    [
        ("<img onerror=x>", "`<img onerror=x>`"),
        ("https://evil.example", "`https://evil.example`"),
        ("www.evil.example", "`www.evil.example`"),
        ("*x* and _x_", "`*x* and _x_`"),
        ("use `code`", "`use code`"),
        ("a\u202eb", "`ab`"),
        ("a\x1b[31mb\x85c", "`a[31mb c`"),
        ("[x](y)", "`[x](y)`"),
        ("a|b", r"`a\|b`"),
        ("  spaced \n out ", "`spaced out`"),
        ("Part\nOne\ttwo", "`Part One two`"),
        ("a\x85b\u2028c\xa0d\re", "`a b c d e`"),
        ("zero\u200bwidth", "`zerowidth`"),
        ("   ", ""),
    ],
)
def test_audit_cells_are_inert_code_spans(text: str, cell: str) -> None:
    row = audit.render([audit.PromotionRecord("C", text, "p", (), 1)]).splitlines()[-1]

    assert row == f"| `C` | {cell} | `p` |  | 1 |"


def test_audit_cell_is_length_capped() -> None:
    row = audit.render([audit.PromotionRecord("C", "x" * 500, "p", (), 1)]).splitlines()[-1]

    assert row == f"| `C` | `{'x' * 199}…` | `p` |  | 1 |"


def test_audit_render_lists_classes_and_level() -> None:
    record = audit.PromotionRecord("C|1", "Big", "div", ("a", "b"), 2)

    row = audit.render([record]).splitlines()[-1]

    assert row == r"| `C\|1` | `Big` | `div` | `a b` | 2 |"


def test_inline_size_fallback_still_works(tmp_path: Path) -> None:
    specs = [ChapterSpec("Chapter One", '<div style="font-size:30px">Big Title</div><p>x</p>')]
    epub = build_epub(tmp_path / "inline.epub", "Inline", specs)

    rendered = convert(read_epub(epub), extensions=["fix-headings"])

    assert "\n## Big Title\n" in rendered.text
    assert [record.level for record in rendered.promotions] == [1]


def test_inline_fallback_applies_alongside_a_stylesheet(tmp_path: Path) -> None:
    body = '<div style="font-size:30px">Big Title</div><div class="class-section">Sec</div>'
    specs = [ChapterSpec("Chapter One", body)]
    epub = build_epub(
        tmp_path / "mixed.epub", "Mixed", specs, stylesheets=(CSS_HEADINGS_STYLESHEET,)
    )

    rendered = convert(read_epub(epub), extensions=["fix-headings"])

    assert [(record.text, record.level) for record in rendered.promotions] == [
        ("Big Title", 1),
        ("Sec", 2),
    ]


def test_classify_reads_a_stylesheet_of_a_real_books_size() -> None:
    filler = ".f{color:red;margin:0;padding:0;border:0}" * 4_000

    assert css_headings.classify(f"{filler}.late{{font-size:2rem}}") == {"late": 1}


def test_real_chapter_title_is_kept_when_first_block_is_promoted(tmp_path: Path) -> None:
    rendered = convert(
        read_epub(build_css_headings_epub(tmp_path / "styled.epub")), extensions=["fix-headings"]
    )

    assert [chapter.title for chapter in rendered.chapters] == ["Chapter One"]


def test_classify_ignores_rules_past_the_size_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(css_classes, "MAX_STYLESHEET_CHARS", 200)
    sheet = f".early{{font-size:2rem}}{' ' * 300}.late{{font-size:3rem}}"

    assert css_headings.classify(sheet) == {"early": 1}


def _first_block_promoted(tmp_path: Path, title: str, *extensions: str, labelled: bool = True):
    body = '<div class="class-part">Dedication</div><div class="class-body">For you.</div>'
    epub = build_epub(
        tmp_path / "t.epub",
        "T",
        [ChapterSpec(title, body)],
        stylesheets=(CSS_HEADINGS_STYLESHEET,),
        labelled=labelled,
    )
    return convert(read_epub(epub), extensions=list(extensions))


def test_a_stem_fallback_title_is_retitled_from_the_promoted_first_block(tmp_path: Path) -> None:
    rendered = _first_block_promoted(tmp_path, "ignored", "fix-headings", labelled=False)

    assert [chapter.title for chapter in rendered.chapters] == ["Dedication"]
    assert rendered.body.count("Dedication") == 1
    assert "ch0" not in rendered.text


def test_retitling_survives_other_extensions_rebuilding_the_chapter(tmp_path: Path) -> None:
    names = ("remove-footnotes", "fix-broken-links", "reformat-toc", "fix-headings")
    rendered = _first_block_promoted(tmp_path, "ignored", *names, labelled=False)

    assert [chapter.title for chapter in rendered.chapters] == ["Dedication"]


@pytest.mark.parametrize(
    "title",
    [
        "Part3",
        "Section2",
        "ch1",
        "xhtml-0-2",
        "chapter_01",
        "1984",
        "Web3",
        "COVID-19",
        "A1",
        "3.1",
    ],
)
def test_an_explicit_label_is_never_overwritten(tmp_path: Path, title: str) -> None:
    rendered = _first_block_promoted(tmp_path, title, "fix-headings")

    assert [chapter.title for chapter in rendered.chapters] == [title]


def test_a_stem_fallback_title_is_left_alone_without_fix_headings(tmp_path: Path) -> None:
    rendered = _first_block_promoted(tmp_path, "ignored", labelled=False)

    assert [chapter.title for chapter in rendered.chapters] == ["ch0"]


def test_uppercase_does_not_split_a_size_tie() -> None:
    sheet = ".a{font-size:2rem}.b{font-size:2rem;text-transform:uppercase}.c{font-size:1.5rem}"

    assert css_headings.classify(sheet) == {"a": 1, "b": 1, "c": 2}


def test_uppercase_ranks_after_size_not_before() -> None:
    sheet = ".big{font-size:2rem}.small{font-size:1.5rem;text-transform:uppercase}"

    assert css_headings.classify(sheet) == {"big": 1, "small": 2}
