"""Linear-time scanner for the top-level rules of an untrusted stylesheet.

It is not a CSS parser. It strips comments, skips at-rules (``@media``, ``@import``,
...) and yields ``(selector, body)`` for each qualified rule, using only ``str.find``
and a single-character regex so work and memory stay linear in the input size.
"""

import re
from collections.abc import Iterator

_MAX_SCANNED_BLOCKS = 200_000
_MAX_SELECTOR_CHARS = 200
_BRACES = re.compile(r"[{}]")
_PRELUDE_NOISE = "} \t\r\n"


def _without_comments(css: str) -> str:
    """Return *css* with ``/* ... */`` comments removed; an unclosed one drops the rest."""
    parts: list[str] = []
    position = 0
    while True:
        start = css.find("/*", position)
        if start < 0:
            parts.append(css[position:])
            return " ".join(parts)
        parts.append(css[position:start])
        end = css.find("*/", start + 2)
        if end < 0:
            return " ".join(parts)
        position = end + 2


def _after_block(css: str, opening: int) -> int:
    """Return the index just past the brace closing the block opened at *opening*, or -1."""
    depth = 0
    for brace in _BRACES.finditer(css, opening):
        depth += 1 if brace.group() == "{" else -1
        if depth == 0:
            return brace.end()
    return -1


def _after_at_rule(css: str, start: int, opening: int) -> int:
    """Return where scanning resumes after the at-rule spanning *start* to the ``{`` at *opening*.

    A statement at-rule (``@import ...;``) ends at its semicolon; a block at-rule ends at
    its matching brace. ``-1`` means the rest of the input belongs to the at-rule.
    """
    semicolon = css.find(";", start, opening)
    return semicolon + 1 if semicolon >= 0 else _after_block(css, opening)


Rule = tuple[str, str]


def _step(text: str, position: int) -> tuple[int, Rule | None]:
    """Scan one block from *position*; return the next position (-1 to stop) and its rule."""
    opening = text.find("{", position)
    if opening < 0:
        return -1, None
    prelude = text[position:opening].lstrip(_PRELUDE_NOISE).rstrip()
    if prelude.startswith("@"):
        return _after_at_rule(text, position, opening), None
    closing = text.find("}", opening + 1)
    if closing < 0:
        return -1, None
    if len(prelude) > _MAX_SELECTOR_CHARS:
        return closing + 1, None
    return closing + 1, (prelude, text[opening + 1 : closing])


def rules(css: str) -> Iterator[Rule]:
    """Yield ``(selector, body)`` for each top-level qualified rule, in linear time.

    Parameters
    ----------
    css:
        Stylesheet text. At most 200,000 blocks are scanned and selectors longer than
        200 characters are skipped.
    """
    text = _without_comments(css)
    position = 0
    for _ in range(_MAX_SCANNED_BLOCKS):
        position, rule = _step(text, position)
        if position < 0:
            return
        if rule is not None:
            yield rule


def _clean(raw: str) -> str:
    """Return a declaration value lowercased, without ``!important`` or anything after ``!``."""
    return raw.split("!", 1)[0].strip().lower()


def declarations(body: str) -> dict[str, str]:
    """Return the last value of each declaration in *body*, names and values lowercased.

    ``!important`` and anything after it is dropped from the value.
    """
    found: dict[str, str] = {}
    for declaration in body.split(";"):
        name, colon, raw = declaration.partition(":")
        if colon:
            found[name.strip().lower()] = _clean(raw)
    return found
