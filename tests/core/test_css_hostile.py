"""Hostile and large stylesheets stay fast and small: classification work is linear."""

import time
import tracemalloc
from collections.abc import Callable
from types import MappingProxyType

import pytest

from md_studio.core.extensions import css_headings

_ONE_MIB = 1_048_576
_WALL_CLOCK_LIMIT_S = 2.0
_PEAK_BYTES_LIMIT = 150_000_000

_REAL_FILLER = ".f{color:red;margin:0;padding:0;border:0}"


def _tiny_rules() -> str:
    return "".join(f".c{index}{{font-size:2em}}" for index in range(60_000))


def _nested_media() -> str:
    return "@media screen{" * 70_000


def _empty_rules() -> str:
    return "a{}" * 350_000


def _huge_selector_list() -> str:
    return f"{','.join(f'.c{index}' for index in range(150_000))}{{font-size:2rem}}"


def _chained_classes() -> str:
    return f"{'.a' * 150_000}{{font-size:2rem}}"


def _open_braces() -> str:
    return "{" * _ONE_MIB


def _unclosed_comments() -> str:
    return "/*" * (_ONE_MIB // 2)


def _closed_comments() -> str:
    return "/**/" * (_ONE_MIB // 4)


def _stray_close_braces() -> str:
    return "}" * _ONE_MIB


def _unclosed_declarations() -> str:
    return f".a{{font-size:2rem;{'x:' * 400_000}"


_HOSTILE: MappingProxyType[str, Callable[[], str]] = MappingProxyType({
    "tiny-rules": _tiny_rules,
    "nested-media": _nested_media,
    "empty-rules": _empty_rules,
    "selector-list": _huge_selector_list,
    "chained-classes": _chained_classes,
    "open-braces": _open_braces,
    "unclosed-comments": _unclosed_comments,
    "closed-comments": _closed_comments,
    "stray-close-braces": _stray_close_braces,
    "unclosed-declarations": _unclosed_declarations,
})


@pytest.mark.parametrize("name", sorted(_HOSTILE))
def test_hostile_stylesheet_classifies_within_two_seconds(name: str) -> None:
    stylesheet = _HOSTILE[name]()
    started = time.perf_counter()

    levels = css_headings.classify(stylesheet)

    assert time.perf_counter() - started < _WALL_CLOCK_LIMIT_S
    assert isinstance(levels, dict)


def test_nested_media_stays_small_in_memory() -> None:
    stylesheet = _nested_media()
    tracemalloc.start()
    css_headings.classify(stylesheet)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()

    assert peak < _PEAK_BYTES_LIMIT


def test_tiny_rules_are_capped_and_still_classify() -> None:
    levels = css_headings.classify(_tiny_rules())

    assert 0 < len(levels) <= 20_000
    assert set(levels.values()) == {1}


def test_class_selector_pattern_is_linear_on_pathological_input() -> None:
    pathological = f".{'a' * 1_000_000}!"
    started = time.perf_counter()

    assert css_headings.CLASS_SELECTOR.fullmatch(pathological) is None
    assert css_headings.SIZE.fullmatch(f"{'9' * 1_000_000}x") is None
    assert time.perf_counter() - started < _WALL_CLOCK_LIMIT_S


_TIERS = (("2.333rem", 1), ("1.667rem", 2), ("1.333rem", 3))


def _real_looking_stylesheet() -> str:
    return "".join(
        f".class-0-{index}{{font-size:{_TIERS[index % 3][0]};margin:0}}{_REAL_FILLER * 40}"
        for index in range(95)
    )


def test_real_looking_stylesheet_still_classifies_every_class() -> None:
    stylesheet = _real_looking_stylesheet()
    started = time.perf_counter()

    levels = css_headings.classify(stylesheet)

    assert len(stylesheet) > 150_000
    assert time.perf_counter() - started < _WALL_CLOCK_LIMIT_S
    assert levels == {f"class-0-{index}": _TIERS[index % 3][1] for index in range(95)}


@pytest.mark.parametrize(
    ("stylesheet", "expected"),
    [
        (".a { font-size : 2REM ; FONT-WEIGHT: BOLD } ", {"a": 1}),
        (".a{font-size:2rem !important}", {"a": 1}),
        (".a{font-size:1rem;font-size:2rem}", {"a": 1}),
        ("/* .a{font-size:2rem} */.b{font-size:2rem}", {"b": 1}),
        ("@media print{.a{font-size:2rem}}.b{font-size:2rem}", {"b": 1}),
        ("@import 'x.css';.a{font-size:2rem}", {"a": 1}),
        ("}.a{font-size:2rem}", {"a": 1}),
        (".a,.b{font-size:2rem}", {}),
        ("div.a{font-size:2rem}", {}),
        (".a{font-size:calc(2rem)}", {}),
    ],
)
def test_scanner_reads_simple_rules_like_a_css_parser(
    stylesheet: str, expected: dict[str, int]
) -> None:
    assert css_headings.classify(stylesheet) == expected
