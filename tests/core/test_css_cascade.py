"""CSS fidelity of the classifier: selector lists, cascade, sheets, units, multi-class."""

import time
from pathlib import Path

import pytest

from md_studio.core.convert import convert
from md_studio.core.document import STYLESHEET_SEPARATOR
from md_studio.core.extensions import css_headings
from md_studio.readers.epub import read_epub
from tests.readers._epub import CSS_HEADINGS_STYLESHEET, ChapterSpec, build_epub


@pytest.mark.parametrize(
    ("stylesheet", "expected"),
    [
        (".a, .b {font-size:2em}", {"a": 1, "b": 1}),
        (".a,\n.b ,.c{font-size:2em}", {"a": 1, "b": 1, "c": 1}),
        (".a, p.t, .c .d {font-size:2em}", {"a": 1}),
        ("p.t{font-size:2em}.a.b{font-size:2em}", {}),
        (".a{font-size:2rem}.a{font-size:1rem}", {}),
        (".a{font-size:1.2rem}.a{font-weight:bold}", {"a": 1}),
        (".a{font-size:2rem}.a{color:red}", {"a": 1}),
        (".a{font-size:2rem}.b{font-size:1.5rem}.a, .b{font-weight:bold}", {"a": 1, "b": 2}),
    ],
)
def test_classify_merges_declarations_per_class(stylesheet: str, expected: dict[str, int]) -> None:
    assert css_headings.classify(stylesheet) == expected


@pytest.mark.parametrize(
    "broken",
    ["a{", ".x{font-size:2rem", "/* never closed", '.x{content:"never closed', "@media x{.y{"],
)
def test_a_broken_sheet_does_not_swallow_the_next_one(broken: str) -> None:
    stylesheet = STYLESHEET_SEPARATOR.join((broken, ".late{font-size:2rem}"))

    assert css_headings.classify(stylesheet).get("late") == 1


def test_cascade_spans_sheets() -> None:
    stylesheet = STYLESHEET_SEPARATOR.join((".a{font-size:1.2rem}", ".a{font-weight:bold}"))

    assert css_headings.classify(stylesheet) == {"a": 1}


@pytest.mark.parametrize(
    ("declarations", "level"),
    [
        ("font-size:20.8px", 1),
        ("font-size:15.6pt", 1),
        ("font-size:130%", 1),
        ("font-size:1.29rem", None),
        ("font-size:1.3rem", 1),
        ("font-size:1.09rem;font-weight:bold", None),
        ("font-size:1.1rem;font-weight:bold", 1),
        ("font-size:1.1rem;font-weight:600", 1),
        ("font-size:1.1rem;font-weight:700", 1),
        ("font-size:1.1rem;font-weight:800", 1),
        ("font-size:1.1rem;font-weight:900", 1),
        ("font-size:1.1rem;font-weight:semibold", 1),
        ("font-size:1.1rem;font-weight:bolder", None),
        ("font-size:1.1rem;font-weight:500", None),
        ("font-size:1.1rem;font-weight:normal", None),
        ("font-size:1.2rem", None),
        ("font-size:2rem !important", 1),
        ("font-size:calc(2rem)", None),
        ("font-size:large", None),
    ],
)
def test_units_and_thresholds(declarations: str, level: int | None) -> None:
    expected = {} if level is None else {"a": level}

    assert css_headings.classify(f".a{{{declarations}}}") == expected


def _paragraph_levels(tmp_path: Path, classes: str, stylesheet: str) -> list[int]:
    body = f'<div class="{classes}">Title</div><div class="class-body">text</div>'
    epub = build_epub(
        tmp_path / "m.epub", "M", [ChapterSpec("Chapter One", body)], stylesheets=(stylesheet,)
    )
    rendered = convert(read_epub(epub), extensions=["fix-headings"])
    return [record.level for record in rendered.promotions]


@pytest.mark.parametrize(
    ("classes", "expected"),
    [("class-sub class-part", [1]), ("class-part class-sub", [1]), ("x class-sub", [3])],
)
def test_element_with_several_heading_classes_takes_the_most_prominent_level(
    tmp_path: Path, classes: str, expected: list[int]
) -> None:
    assert _paragraph_levels(tmp_path, classes, CSS_HEADINGS_STYLESHEET) == expected


def test_media_only_heading_class_stays_a_paragraph(tmp_path: Path) -> None:
    stylesheet = "@media screen{.class-part{font-size:2.333rem}}"
    body = '<div class="class-part">Part One</div>'
    epub = build_epub(
        tmp_path / "m.epub", "M", [ChapterSpec("Chapter One", body)], stylesheets=(stylesheet,)
    )

    rendered = convert(read_epub(epub), extensions=["fix-headings"])

    assert rendered.promotions == ()
    assert "\nPart One\n" in rendered.text


_FAST_SECONDS = 0.3


@pytest.mark.parametrize(
    ("stylesheet", "expected"),
    [
        (".a{font-size:2rem;font-size:calc(2rem)}", {"a": 1}),
        (".a{font-size:2rem;font-size:clamp(1rem,2vw,3rem)}", {"a": 1}),
        (".a{font-size:2rem}.a{font-size:var(--x)}", {"a": 1}),
        (".a{font-size:2rem}.a{font-size:inherit}", {"a": 1}),
        (".a{font-size:calc(2rem)}", {}),
        (".a{font-size:2rem!important}.a{font-size:1rem}", {"a": 1}),
        (".a{font-size:2rem !important;font-size:1rem}", {"a": 1}),
        (".a{font-size:1rem!important}.a{font-size:2rem!important}", {"a": 1}),
        (".a{font-size:2rem}.a{font-size:1rem!important}", {}),
        (".a{font-size:1.2rem!important}.a{font-weight:bold}.a{font-weight:normal!important}", {}),
    ],
)
def test_cascade_ignores_unparseable_sizes_and_honors_important(
    stylesheet: str, expected: dict[str, int]
) -> None:
    assert css_headings.classify(stylesheet) == expected


def test_bare_separators_are_skipped_quickly() -> None:
    started = time.perf_counter()

    levels = css_headings.classify(STYLESHEET_SEPARATOR * 1_048_576)

    assert levels == {}
    assert time.perf_counter() - started < _FAST_SECONDS


def test_oversize_rules_across_sheets_produce_one_note() -> None:
    body = "color:red;" * 210
    sheets = ["".join(f".big{{{body}}}" for _ in range(count + 1)) for count in range(20)]
    expected_total = sum(range(1, 21))

    report = css_headings.classify_report(STYLESHEET_SEPARATOR.join(sheets))

    oversize = [note for note in report.notes if "oversize" in note]
    assert oversize == [f"{expected_total} oversize rule(s) were ignored"]


def _many_irrelevant_classes(rules: int) -> str:
    return "".join(
        f"{','.join(f'.c{rule}x{index}' for index in range(64))}{{color:red}}"
        for rule in range(rules)
    )


def test_rules_without_relevant_declarations_do_not_use_the_class_budget() -> None:
    stylesheet = f"{_many_irrelevant_classes(313)}.heading{{font-size:2rem}}"

    report = css_headings.classify_report(stylesheet)

    assert dict(report.levels) == {"heading": 1}
    assert report.notes == ()


def test_reaching_the_class_limit_is_noted_once() -> None:
    sizes = "".join(
        f"{','.join(f'.c{rule}x{index}' for index in range(64))}{{font-size:1rem}}"
        for rule in range(313)
    )
    stylesheet = f"{sizes}.heading{{font-size:2rem}}.other{{font-size:2rem}}"

    report = css_headings.classify_report(stylesheet)

    assert "heading" not in report.levels
    assert [note for note in report.notes if "classes" in note] == [
        "more than 20000 classes; the rest were ignored"
    ]
