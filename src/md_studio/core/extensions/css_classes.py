"""Gather, per class name, the font declarations an untrusted stylesheet gives it.

Declarations of one class are merged across all its rules and sheets, later ones
winning, so the caller can decide once per class whether it styles a heading.
"""

import re

from md_studio.core.document import STYLESHEET_SEPARATOR
from md_studio.core.extensions import css_scan

MAX_STYLESHEET_CHARS = 1_048_576
_MAX_RULES = 20_000
_MAX_CLASSES = 20_000
_MAX_SELECTORS_PER_RULE = 64
_RELEVANT = ("font-size", "font-weight", "text-transform")
_CLASS_SELECTOR = re.compile(r"\.(-?[A-Za-z_][\w-]*)")

Declarations = dict[str, str]


def _class_names(selector: str) -> list[str]:
    """Return the class names of each simple ``.class`` entry of a selector list."""
    entries = selector.split(",", _MAX_SELECTORS_PER_RULE)[:_MAX_SELECTORS_PER_RULE]
    matches = (_CLASS_SELECTOR.fullmatch(entry.strip()) for entry in entries)
    return [match.group(1) for match in matches if match is not None]


def _merge(found: dict[str, Declarations], selector: str, body: str) -> None:
    """Merge the relevant declarations of *body* into each class of *selector* (later wins)."""
    declared = css_scan.declarations(body)
    relevant = {key: declared[key] for key in _RELEVANT if key in declared}
    for name in _class_names(selector):
        if name in found or len(found) < _MAX_CLASSES:
            found.setdefault(name, {}).update(relevant)


def collect(stylesheet: str, notes: list[str]) -> dict[str, Declarations]:
    """Scan every sheet of *stylesheet* and return merged declarations by class name.

    Parameters
    ----------
    stylesheet:
        Sheets joined by ``STYLESHEET_SEPARATOR``; each is scanned on its own so a broken
        sheet cannot swallow the next. Only the first 1 MiB and 20,000 rules are read.
    notes:
        Receives a description of anything that was cut off or could not be read.
    """
    found: dict[str, Declarations] = {}
    scanned = 0
    if len(stylesheet) > MAX_STYLESHEET_CHARS:
        notes.append("stylesheet is larger than 1 MiB; the rest was ignored")
    for sheet in stylesheet[:MAX_STYLESHEET_CHARS].split(STYLESHEET_SEPARATOR):
        for selector, body in css_scan.rules(sheet, notes):
            if scanned >= _MAX_RULES:
                notes.append(f"more than {_MAX_RULES} rules; the rest were ignored")
                return found
            scanned += 1
            _merge(found, selector, body)
    return found
