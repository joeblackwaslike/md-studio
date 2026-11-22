"""Gather, per class name, the font declarations an untrusted stylesheet gives it.

Declarations of one class are merged across all its rules and sheets, later ones
winning, so the caller can decide once per class whether it styles a heading.
"""

import re
from collections.abc import Iterator
from itertools import chain, islice

from md_studio.core.document import STYLESHEET_SEPARATOR
from md_studio.core.extensions import css_scan
from md_studio.core.extensions.css_declarations import (
    Declared,
    Merged,
    add_class,
    declaration_list,
    override,
)
from md_studio.core.extensions.css_size import size_in_rem

MAX_STYLESHEET_CHARS = 1_048_576
_MAX_RULES = 20_000
_MAX_CLASSES = 20_000
_MAX_SELECTORS_PER_RULE = 64
_FONT_SIZE = "font-size"
_RELEVANT = (_FONT_SIZE, "font-weight", "text-transform")
_CLASS_SELECTOR = re.compile(r"\.(-?[A-Za-z_][\w-]*)")

Declarations = dict[str, str]


def _class_names(selector: str) -> list[str]:
    """Return the class names of each simple ``.class`` entry of a selector list."""
    entries = selector.split(",", _MAX_SELECTORS_PER_RULE)[:_MAX_SELECTORS_PER_RULE]
    matches = (_CLASS_SELECTOR.fullmatch(entry.strip()) for entry in entries)
    return [match.group(1) for match in matches if match is not None]


def _usable(name: str, declared: Declared) -> bool:
    """Return whether a declaration matters; a font size that is not a plain length is dropped."""
    if name == _FONT_SIZE:
        return size_in_rem(declared.text) is not None
    return name in _RELEVANT


def _relevant(body: str) -> dict[str, Declared]:
    """Return the winning relevant declarations of *body*, ignoring unparseable ones."""
    kept: dict[str, Declared] = {}
    for name, declared in declaration_list(body):
        if _usable(name, declared):
            override(kept, name, declared)
    return kept


def _merge(found: Merged, selector: str, body: str) -> bool:
    """Merge the relevant declarations of *body* into each class of *selector* (cascade).

    Rules with nothing relevant allocate no entries. Returns whether the class limit made
    it refuse a new class.
    """
    relevant = _relevant(body)
    names = _class_names(selector) if relevant else []
    accepted = [add_class(found, name, relevant, _MAX_CLASSES) for name in names]
    return not all(accepted)


def _rules(stylesheet: str, notes: list[str], dropped: list[int]) -> Iterator[css_scan.Rule]:
    """Yield the first rules of the non-empty sheets in turn, noting when there were more."""
    sheets = filter(None, stylesheet.split(STYLESHEET_SEPARATOR))
    rules = chain.from_iterable(css_scan.rules(sheet, notes, dropped) for sheet in sheets)
    yield from islice(rules, _MAX_RULES)
    if next(rules, None) is not None:
        notes.append(f"more than {_MAX_RULES} rules; the rest were ignored")


def _scan(stylesheet: str, notes: list[str]) -> Merged:
    """Merge declarations per class over the rules of all sheets; note what was dropped."""
    found: Merged = {}
    dropped: list[int] = []
    refused = False
    for selector, body in _rules(stylesheet, notes, dropped):
        refused = _merge(found, selector, body) or refused
    if refused:
        notes.append(f"more than {_MAX_CLASSES} classes; the rest were ignored")
    if sum(dropped):
        notes.append(f"{sum(dropped)} oversize rule(s) were ignored")
    return found


def collect(stylesheet: str, notes: list[str]) -> dict[str, Declarations]:
    """Scan every sheet of *stylesheet* and return merged declarations by class name.

    Declarations cascade: later ones win, an ``!important`` one is only replaced by another,
    and font sizes that are not plain lengths are ignored.

    Parameters
    ----------
    stylesheet:
        Sheets joined by ``STYLESHEET_SEPARATOR``; each is scanned on its own so a broken
        sheet cannot swallow the next. Only the first 1 MiB and 20,000 rules are read.
    notes:
        Receives a description of anything that was cut off or could not be read.
    """
    if len(stylesheet) > MAX_STYLESHEET_CHARS:
        notes.append("stylesheet is larger than 1 MiB; the rest was ignored")
    merged = _scan(stylesheet[:MAX_STYLESHEET_CHARS], notes)
    return {
        name: {key: declared.text for key, declared in props.items()}
        for name, props in merged.items()
    }
