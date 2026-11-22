"""Classify CSS classes that style headings, by font size, weight and case.

Some EPUBs mark headings with ``<div class="x">`` whose stylesheet gives the class a
large font size instead of using ``<h1>``-``<h6>``. :func:`classify` ranks such classes
into heading levels. The stylesheet is untrusted, so it is read by a small linear
scanner (no CSS parser): only top-level ``.class { ... }`` rules are looked at, comments
and at-rules (``@media``, ``@import``, ...) are skipped, and every step is size-capped.
Declarations for a class are merged across its rules (later ones win) before deciding
whether it styles a heading. Sheets are scanned independently, so a broken sheet cannot
swallow the next one.
"""

import re
from functools import lru_cache
from types import MappingProxyType
from typing import NamedTuple

from md_studio.core.extensions import css_classes

_MAX_VALUE_CHARS = 32
_MAX_REM = 1000.0
_MAX_LEVEL = 6
_MIN_HEADING_REM = 1.3
_MIN_BOLD_HEADING_REM = 1.1
_SAME_LEVEL_REM = 0.1
_PX_PER_REM = 16
_PT_PER_REM = 12
_PERCENT = 100
_UNITS_PER_REM = MappingProxyType({
    "rem": 1,
    "em": 1,
    "px": _PX_PER_REM,
    "pt": _PT_PER_REM,
    "%": _PERCENT,
})
_PRECISION = 9
_BOLD_WEIGHTS = frozenset(("bold", "semibold", "600", "700", "800", "900"))
_SIZE = re.compile(r"(\d+(?:\.\d+)?|\.\d+)(rem|em|px|pt|%)")


class _Candidate(NamedTuple):
    """A class styled large or bold enough to be a heading, ordered by rank."""

    size: float
    uppercase: bool
    name: str


class ClassifyReport(NamedTuple):
    """Heading levels by class name, plus notes on any CSS that could not be used."""

    levels: MappingProxyType[str, int]
    notes: tuple[str, ...]


def _size_in_rem(raw: str) -> float | None:
    """Return a CSS font size in rem, or ``None`` when it is not a plain length."""
    if len(raw) > _MAX_VALUE_CHARS:
        return None
    match = _SIZE.fullmatch(raw)
    if match is None:
        return None
    number, unit = match.groups()
    return round(float(number) / _UNITS_PER_REM[unit], _PRECISION)


def _candidate(declared: tuple[str, dict[str, str]]) -> _Candidate | None:
    """Return the heading candidate for a ``(class name, merged declarations)`` pair, if any."""
    name, props = declared
    size = _size_in_rem(props.get("font-size", ""))
    if size is None or size > _MAX_REM:
        return None
    bold = props.get("font-weight", "") in _BOLD_WEIGHTS
    if size < _MIN_HEADING_REM and not (bold and size >= _MIN_BOLD_HEADING_REM):
        return None
    return _Candidate(size, props.get("text-transform", "") == "uppercase", name)


def _assign_levels(ranked: list[_Candidate]) -> dict[str, int]:
    """Give each candidate (largest first) a level; sizes within 0.1rem share one."""
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
def classify_report(stylesheet: str) -> ClassifyReport:
    """Classify *stylesheet* and report any CSS that could not be used.

    The result is cached, so the per-chapter calls of one conversion parse once.

    Parameters
    ----------
    stylesheet:
        CSS text, possibly malformed or hostile; sheets are separated by
        :data:`md_studio.core.document.STYLESHEET_SEPARATOR`. Only the first 1 MiB and
        the first 20000 rules are read; ``@import`` targets are never fetched.
        Comments, at-rules and selectors that are not a plain ``.class`` (alone or in a
        comma list) are ignored.

    Returns
    -------
    ClassifyReport
        Class name to level 1-6, and de-duplicated notes about ignored CSS.
    """
    notes: list[str] = []
    collected = css_classes.collect(stylesheet, notes)
    found = filter(None, map(_candidate, collected.items()))
    levels = _assign_levels(sorted(found, reverse=True))
    return ClassifyReport(MappingProxyType(levels), tuple(dict.fromkeys(notes)))


def classify(stylesheet: str) -> dict[str, int]:
    """Map heading class names to heading levels 1-6 using the stylesheet's rules.

    A class qualifies when its font size is at least 1.3rem, or at least 1.1rem and
    bold (``bold``, ``semibold``, 600-900). Qualifying classes are ranked largest first
    (uppercase breaks ties); sizes within 0.1rem share a level, and levels deeper than
    6 clamp to 6. ``em`` and ``%`` are treated as relative to the root font size, ``px``
    and ``pt`` are converted at 16px and 12pt per rem.

    Parameters
    ----------
    stylesheet:
        CSS text; see :func:`classify_report` for the limits.

    Returns
    -------
    dict[str, int]
        Class name to level, or ``{}`` when nothing qualifies.
    """
    return dict(classify_report(stylesheet).levels)
