"""Classify CSS classes that style headings, by font size, weight and case.

Some EPUBs mark headings with ``<div class="x">`` whose stylesheet gives the class a
large font size instead of using ``<h1>``-``<h6>``. :func:`classify` ranks such classes
into heading levels. The stylesheet is untrusted, so parsing is size-bounded, never
fetches ``@import`` targets, and any parser failure means "no classification".
"""

import logging
import re
from functools import lru_cache
from itertools import islice
from types import MappingProxyType
from typing import NamedTuple

_MAX_STYLESHEET_CHARS = 1_048_576
_MAX_RULES = 20_000
_MAX_LEVEL = 6
_MIN_HEADING_REM = 1.3
_MIN_BOLD_HEADING_REM = 1.1
_SAME_LEVEL_REM = 0.1
_PX_PER_REM = 16
_PT_PER_REM = 12
_PERCENT = 100
_REM_PER_UNIT = MappingProxyType({
    "rem": 1.0,
    "em": 1.0,
    "px": 1 / _PX_PER_REM,
    "pt": 1 / _PT_PER_REM,
    "%": 1 / _PERCENT,
})
_BOLD_WEIGHTS = frozenset(("bold", "semibold", "600", "700", "800", "900"))
_CLASS_SELECTOR = re.compile(r"\.(-?[A-Za-z_][\w-]*)")
_SIZE = re.compile(r"(\d+(?:\.\d+)?|\.\d+)(rem|em|px|pt|%)")


class _Candidate(NamedTuple):
    """A class styled large or bold enough to be a heading, ordered by rank."""

    size: float
    uppercase: bool
    name: str


def _size_in_rem(raw: str) -> float | None:
    """Return a CSS font size in rem, or ``None`` when it is not a plain length."""
    match = _SIZE.fullmatch(raw.strip().lower())
    if match is None:
        return None
    return float(match.group(1)) * _REM_PER_UNIT[match.group(2)]


def _candidate(rule: object) -> _Candidate | None:
    """Return the heading candidate described by a style *rule*, if any."""
    selector = _CLASS_SELECTOR.fullmatch(getattr(rule, "selectorText", ""))
    if selector is None:
        return None
    style = getattr(rule, "style")  # noqa: B009 -- cssutils is untyped
    size = _size_in_rem(style.getPropertyValue("font-size"))
    if size is None or size > _MAX_STYLESHEET_CHARS:
        return None
    bold = style.getPropertyValue("font-weight").strip().lower() in _BOLD_WEIGHTS
    if size < _MIN_HEADING_REM and not (bold and size >= _MIN_BOLD_HEADING_REM):
        return None
    uppercase = style.getPropertyValue("text-transform").strip().lower() == "uppercase"
    return _Candidate(size, uppercase, selector.group(1))


def _parse_candidates(stylesheet: str) -> dict[str, _Candidate]:
    """Parse *stylesheet* and return its heading candidates by class name."""
    import cssutils  # noqa: PLC0415 -- lazy: parsing machinery stays off core import

    parser = cssutils.CSSParser(
        loglevel=logging.CRITICAL, raiseExceptions=False, validate=False, fetcher=lambda _url: None
    )
    sheet = parser.parseString(stylesheet[:_MAX_STYLESHEET_CHARS])
    found = (_candidate(rule) for rule in islice(sheet.cssRules, _MAX_RULES))
    return {entry.name: entry for entry in found if entry is not None}


def _assign_levels(candidates: dict[str, _Candidate]) -> dict[str, int]:
    """Rank candidates by size (then uppercase) and group sizes within 0.1rem."""
    ranked = sorted(candidates.values(), reverse=True)
    levels: dict[str, int] = {}
    level = 0
    previous: float | None = None
    for entry in ranked:
        if previous is None or abs(entry.size - previous) >= _SAME_LEVEL_REM:
            level += 1
        previous = entry.size
        levels[entry.name] = min(level, _MAX_LEVEL)
    return levels


@lru_cache(maxsize=2)
def _classify_cached(stylesheet: str) -> MappingProxyType[str, int]:
    """Classify *stylesheet*, treating any parser failure as no classification."""
    try:
        levels = _assign_levels(_parse_candidates(stylesheet))
    except Exception:  # untrusted input: any parser failure means no classification
        levels = {}
    return MappingProxyType(levels)


def classify(stylesheet: str) -> dict[str, int]:
    """Map heading class names to heading levels 1-6 using the stylesheet's rules.

    A class qualifies when its font size is at least 1.3rem, or at least 1.1rem and
    bold. Qualifying classes are ranked largest first (uppercase breaks ties); sizes
    within 0.1rem share a level, and levels deeper than 6 clamp to 6.

    Parameters
    ----------
    stylesheet:
        CSS text, possibly malformed or hostile. Only the first 1 MiB and the first
        20000 rules are read; ``@import`` targets are never fetched.

    Returns
    -------
    dict[str, int]
        Class name to level, or ``{}`` when nothing qualifies or parsing fails.
    """
    return dict(_classify_cached(stylesheet))
