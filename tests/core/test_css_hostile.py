"""Hostile and large stylesheets stay fast and small: classification work is linear."""

import random
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


def _statement_at_rules_then_brace() -> str:
    return "".join(("@a;" * 350_000, "{"))


def _imports_then_brace() -> str:
    return "".join(("@import url(x);" * 70_000, "{"))


def _statement_at_rules_no_brace() -> str:
    return "@a;" * 350_000


def _at_rule_then_empty_rule() -> str:
    return "@a;a{}" * 170_000


def _semicolons_then_brace() -> str:
    return "".join((";" * (_ONE_MIB - 1), "{"))


def _comments_between_at_rules() -> str:
    return "@a;/**/" * 150_000


def _quotes() -> str:
    return '"' * _ONE_MIB


def _escaped_quotes() -> str:
    return "'\\" * 350_000


def _long_unterminated_string() -> str:
    return f'.a{{content:"{"x" * _ONE_MIB}'


def _long_escape_chain() -> str:
    return "".join(('"', r"\a" * 300_000))


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
    "statement-at-rules-then-brace": _statement_at_rules_then_brace,
    "imports-then-brace": _imports_then_brace,
    "statement-at-rules-no-brace": _statement_at_rules_no_brace,
    "at-rule-then-empty-rule": _at_rule_then_empty_rule,
    "semicolons-then-brace": _semicolons_then_brace,
    "comments-between-at-rules": _comments_between_at_rules,
    "quotes": _quotes,
    "escaped-quotes": _escaped_quotes,
    "long-unterminated-string": _long_unterminated_string,
    "long-escape-chain": _long_escape_chain,
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
        (".a,.b{font-size:2rem}", {"a": 1, "b": 1}),
        ("div.a{font-size:2rem}", {}),
        (".a{font-size:calc(2rem)}", {}),
    ],
)
def test_scanner_reads_simple_rules_like_a_css_parser(
    stylesheet: str, expected: dict[str, int]
) -> None:
    assert css_headings.classify(stylesheet) == expected


_SCALING_FAMILIES = MappingProxyType({
    "statement-at-rules": ("@a;", "{"),
    "imports": ("@import url(x);", "{"),
    "semicolons": (";", "{"),
    "at-rule-empty-rule": ("@a;a{}", ""),
    "comments": ("@a;/**/", ""),
    "tiny-rules": (".c{font-size:2em}", ""),
})


def _fresh_elapsed(stylesheet: str) -> float:
    css_headings.classify_report.cache_clear()
    return _elapsed(stylesheet)


def _best_of_three(stylesheet: str) -> float:
    return min(_fresh_elapsed(stylesheet) for _ in range(3))


def _elapsed(stylesheet: str) -> float:
    started = time.perf_counter()
    css_headings.classify(stylesheet)
    return time.perf_counter() - started


@pytest.mark.parametrize("family", sorted(_SCALING_FAMILIES))
def test_work_grows_linearly_with_input_size(family: str) -> None:
    unit, tail = _SCALING_FAMILIES[family]
    small = _best_of_three(unit * (65_536 // len(unit)) + tail)
    large = _best_of_three(unit * (_ONE_MIB // len(unit)) + tail)

    assert large < 60 * max(small, 0.005)


_FUZZ_TOKENS = (
    "@a;", "{", "}", "/*", "*/", '"', "'", "\\", ".a", "a{}", "@media x{", ";", "!", "\n",
    ".b{font-size:2rem}", "font-size:2rem",
)  # fmt: skip


def test_random_token_streams_finish_fast_and_never_raise() -> None:
    rng = random.Random(0)  # noqa: S311 -- seeded fuzz, not security
    for _ in range(25):
        stylesheet = "".join(rng.choices(_FUZZ_TOKENS, k=40_000))[:131_072]
        started = time.perf_counter()

        levels = css_headings.classify(stylesheet)

        assert time.perf_counter() - started < _WALL_CLOCK_LIMIT_S
        assert isinstance(levels, dict)


@pytest.mark.parametrize(
    ("stylesheet", "expected"),
    [
        ('.a{content:"}";font-size:2rem} .b{font-size:3rem}', {"b": 1, "a": 2}),
        (".a{content:'}';font-size:2rem}.b{font-size:3rem}", {"b": 1, "a": 2}),
        ('.a{background:url("data:image/png;base64,{x}")}.b{font-size:2rem}', {"b": 1}),
        (r'.a{content:"a\"}";font-size:2rem}.b{font-size:3rem}', {"b": 1, "a": 2}),
        (".a{content:'x\n}.b{font-size:3rem}", {"b": 1}),
        ('.a{content:"/*"}.b{font-size:3rem}/*"*/', {"b": 1}),
        ('/*"*/.a{font-size:2rem}', {"a": 1}),
    ],
)
def test_scanner_is_aware_of_quoted_strings(stylesheet: str, expected: dict[str, int]) -> None:
    assert css_headings.classify(stylesheet) == expected


@pytest.mark.parametrize(
    ("stylesheet", "expected"),
    [
        (
            r'.a{content:"line\
break}";font-size:2rem}.b{font-size:3rem}',
            {"b": 1, "a": 2},
        ),
        (".a{background:url(it's.png);font-size:2rem}.b{font-size:3rem}", {"b": 1, "a": 2}),
        (".a{background:URL( it's.png );font-size:2rem}.b{font-size:3rem}", {"b": 1, "a": 2}),
        (".a{background:url( 'x}.png' );font-size:2rem}.b{font-size:3rem}", {"b": 1, "a": 2}),
        (".a{background:url(unterminated\n}.b{font-size:3rem}", {"b": 1}),
    ],
)
def test_noise_handling_of_string_continuations_and_unquoted_urls(
    stylesheet: str, expected: dict[str, int]
) -> None:
    assert css_headings.classify(stylesheet) == expected


def test_many_unquoted_urls_stay_linear() -> None:
    unit = "url(a'b "
    small = _best_of_three(unit * 8_000)
    large = _best_of_three(unit * 128_000)

    assert large < 60 * max(small, 0.005)
