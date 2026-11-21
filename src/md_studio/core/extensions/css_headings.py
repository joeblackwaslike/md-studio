"""Classify CSS classes that style headings, by font size, weight and case.

Some EPUBs mark headings with ``<div class="x">`` whose stylesheet gives the class a
large font size instead of using ``<h1>``-``<h6>``. :func:`classify` ranks such classes
into heading levels. The stylesheet is untrusted, so it is read by a small linear
scanner (no CSS parser): only top-level ``.class { ... }`` rules are looked at, comments
and at-rules (``@media``, ``@import``, ...) are skipped, and every step is size-capped.
"""

import re
from functools import lru_cache
from itertools import islice
from types import MappingProxyType
from typing import NamedTuple

from md_studio.core.extensions import css_scan

_MAX_STYLESHEET_CHARS = 1_048_576
_MAX_RULES = 20_000
_MAX_BODY_CHARS = 2_048
_MAX_VALUE_CHARS = 32
_MAX_REM = 1000.0
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
CLASS_SELECTOR = re.compile(r"\.(-?[A-Za-z_][\w-]*)")
SIZE = re.compile(r"(\d+(?:\.\d+)?|\.\d+)(rem|em|px|pt|%)")


class _Candidate(NamedTuple):
    """A class styled large or bold enough to be a heading, ordered by rank."""

    size: float
    uppercase: bool
    name: str


def _size_in_rem(raw: str) -> float | None:
    """Return a CSS font size in rem, or ``None`` when it is not a plain length."""
    if len(raw) > _MAX_VALUE_CHARS:
        return None
    match = SIZE.fullmatch(raw)
    if match is None:
        return None
    return float(match.group(1)) * _REM_PER_UNIT[match.group(2)]


def _candidate(selector: str, body: str) -> _Candidate | None:
    """Return the heading candidate for one ``selector { body }`` rule, if any."""
    matched = CLASS_SELECTOR.fullmatch(selector)
    if matched is None or len(body) > _MAX_BODY_CHARS:
        return None
    props = css_scan.declarations(body)
    size = _size_in_rem(props.get("font-size", ""))
    if size is None or size > _MAX_REM:
        return None
    bold = props.get("font-weight", "") in _BOLD_WEIGHTS
    if size < _MIN_HEADING_REM and not (bold and size >= _MIN_BOLD_HEADING_REM):
        return None
    uppercase = props.get("text-transform", "") == "uppercase"
    return _Candidate(size, uppercase, matched.group(1))


def _parse_candidates(stylesheet: str) -> dict[str, _Candidate]:
    """Scan *stylesheet* and return its heading candidates by class name."""
    found: dict[str, _Candidate] = {}
    rules = islice(css_scan.rules(stylesheet[:_MAX_STYLESHEET_CHARS]), _MAX_RULES)
    for selector, body in rules:
        entry = _candidate(selector, body)
        if entry is not None:
            found[entry.name] = entry
    return found


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
    """Classify *stylesheet*, caching the result for the per-chapter calls of one run."""
    return MappingProxyType(_assign_levels(_parse_candidates(stylesheet)))


def classify(stylesheet: str) -> dict[str, int]:
    """Map heading class names to heading levels 1-6 using the stylesheet's rules.

    A class qualifies when its font size is at least 1.3rem, or at least 1.1rem and
    bold. Qualifying classes are ranked largest first (uppercase breaks ties); sizes
    within 0.1rem share a level, and levels deeper than 6 clamp to 6.

    Parameters
    ----------
    stylesheet:
        CSS text, possibly malformed or hostile. Only the first 1 MiB and the first
        20000 rules are read; ``@import`` targets are never fetched. Comments, at-rules
        and rules whose selector is not a single class are ignored.

    Returns
    -------
    dict[str, int]
        Class name to level, or ``{}`` when nothing qualifies.
    """
    return dict(_classify_cached(stylesheet))
