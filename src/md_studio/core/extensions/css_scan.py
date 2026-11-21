"""Linear-time scanner for the top-level rules of an untrusted stylesheet.

It is not a CSS parser. After comments and string contents are blanked, it walks every
``{``, ``}`` and ``;`` exactly once, tracking brace depth, and yields ``(selector, body)``
for each top-level qualified rule. At-rules (``@media``, ``@import``, ...) are skipped.
The scan only moves forward, so work and memory are linear in the input size.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

from md_studio.core.extensions.css_noise import blank_noise

_MAX_PRELUDE_RAW_CHARS = 4_096
_MAX_SELECTOR_CHARS = 200
_MAX_BODY_CHARS = 2_048
_STRUCTURE = re.compile(r"[{};}]")

Rule = tuple[str, str]


def _selector(prelude: str, body: str) -> Rule | None:
    """Return ``(selector, body)`` for a qualified rule within the size caps, else ``None``."""
    selector = prelude.strip()
    if selector.startswith("@") or len(selector) > _MAX_SELECTOR_CHARS:
        return None
    return None if len(body) > _MAX_BODY_CHARS else (selector, body)


@dataclass(slots=True)
class _Walk:
    """Position of the scan: where the current prelude and body started, and brace depth."""

    start: int = 0
    body_start: int = 0
    depth: int = 0
    prelude: str = ""

    def opened(self, text: str, at: int) -> None:
        """Handle a ``{`` at *at*."""
        if self.depth == 0:
            too_long = at - self.start > _MAX_PRELUDE_RAW_CHARS
            self.prelude = "@" if too_long else text[self.start : at]
            self.body_start = at + 1
        self.depth += 1

    def closed(self, text: str, at: int) -> Rule | None:
        """Handle a ``}`` at *at* inside a block; return the rule it completes, if any."""
        self.depth -= 1
        if self.depth > 0:
            return None
        self.start = at + 1
        return _selector(self.prelude, text[self.body_start : at])

    def step(self, text: str, char: str, at: int) -> Rule | None:
        """Handle the structural *char* at *at*; return a completed rule, if any."""
        if char == "{":
            self.opened(text, at)
        elif char == "}" and self.depth > 0:
            return self.closed(text, at)
        elif self.depth == 0:
            self.start = at + 1
        return None


def rules(css: str) -> Iterator[Rule]:
    """Yield ``(selector, body)`` for each top-level qualified rule, in linear time.

    Parameters
    ----------
    css:
        Stylesheet text. Preludes over 4,096 characters, selectors over 200 and bodies
        over 2,048 are skipped.
    """
    text = blank_noise(css)
    walk = _Walk()
    for token in _STRUCTURE.finditer(text):
        rule = walk.step(text, token.group(), token.start())
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
