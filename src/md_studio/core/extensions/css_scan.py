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
_MAX_SELECTOR_CHARS = 1_024
_MAX_BODY_CHARS = 2_048
_STRUCTURE = re.compile(r"[{};}]")

Rule = tuple[str, str]
Notes = list[str] | None
Counts = list[int] | None


@dataclass(slots=True)
class _Walk:
    """Position of the scan: where the current prelude and body started, and brace depth."""

    start: int = 0
    body_start: int = 0
    depth: int = 0
    prelude: str | None = ""
    dropped: int = 0

    def opened(self, text: str, at: int) -> None:
        """Handle a ``{`` at *at*."""
        if self.depth == 0:
            too_long = at - self.start > _MAX_PRELUDE_RAW_CHARS
            self.prelude = None if too_long else text[self.start : at]
            self.body_start = at + 1
        self.depth += 1

    def closed(self, text: str, at: int) -> Rule | None:
        """Handle a ``}`` at *at* inside a block; return the rule it completes, if any."""
        self.depth -= 1
        if self.depth > 0:
            return None
        self.start = at + 1
        selector = (self.prelude or "").strip()
        body = text[self.body_start : at]
        if selector.startswith("@"):
            return None
        if (
            self.prelude is None
            or len(selector) > _MAX_SELECTOR_CHARS
            or len(body) > _MAX_BODY_CHARS
        ):
            self.dropped += 1
            return None
        return selector, body

    def step(self, text: str, char: str, at: int) -> Rule | None:
        """Handle the structural *char* at *at*; return a completed rule, if any."""
        if char == "{":
            self.opened(text, at)
        elif char == "}" and self.depth > 0:
            return self.closed(text, at)
        elif self.depth == 0:
            self.start = at + 1
        return None


def _notes(walk: _Walk, *, cut_by_comment: bool) -> list[str]:
    """Describe the unclosed constructs the scan ended inside."""
    notes = []
    if cut_by_comment:
        notes.append("stylesheet ends inside an unclosed comment; the rest was ignored")
    if walk.depth > 0:
        notes.append("stylesheet ends inside an unclosed block; that rule was ignored")
    return notes


def rules(css: str, notes: Notes = None, dropped: Counts = None) -> Iterator[Rule]:
    """Yield ``(selector, body)`` for each top-level qualified rule, in linear time.

    Parameters
    ----------
    css:
        Stylesheet text. Preludes over 4,096 characters, selectors over 1,024 and bodies
        over 2,048 are skipped.
    notes:
        When given, receives a description of an unclosed comment or block once the
        iterator is exhausted.
    dropped:
        When given, receives the number of oversize rules skipped, once exhausted.
    """
    text, cut_by_comment = blank_noise(css)
    walk = _Walk()
    for token in _STRUCTURE.finditer(text):
        rule = walk.step(text, token.group(), token.start())
        if rule is not None:
            yield rule
    if notes is not None:
        notes.extend(_notes(walk, cut_by_comment=cut_by_comment))
    if dropped is not None:
        dropped.append(walk.dropped)
