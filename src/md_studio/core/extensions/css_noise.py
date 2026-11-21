"""Blank the comments and string contents of an untrusted stylesheet in linear time.

Braces, semicolons and ``/*`` inside ``content:"}"`` or ``url("data:...")`` must not
confuse the rule scanner, and none of that text matters for classification, so it is
replaced before scanning. Every step moves forward only.
"""

import re
from types import MappingProxyType

_NOISE_START = re.compile(r"/\*|[\"']")
_STRING_END = MappingProxyType({
    '"': re.compile(r'[^"\\\n]*(?:\\.[^"\\\n]*)*"?'),
    "'": re.compile(r"[^'\\\n]*(?:\\.[^'\\\n]*)*'?"),
})


def _noise_step(css: str, opener: str, after: int) -> tuple[str, int]:
    """Return the replacement text and resume position for the noise opened at *after*.

    A resume position of ``-1`` means the rest of the input was dropped (unclosed comment).
    """
    if opener == "/*":
        end = css.find("*/", after)
        return (" ", -1) if end < 0 else (" ", end + 2)
    closing = _STRING_END[opener].match(css, after)
    return '""', after if closing is None else closing.end()


def blank_noise(css: str) -> str:
    """Return *css* with comments replaced by a space and string contents emptied.

    An unclosed comment drops the rest of the input; a string with no closing quote
    ends at the end of its line.
    """
    parts: list[str] = []
    position = 0
    while True:
        found = _NOISE_START.search(css, position)
        if found is None:
            parts.append(css[position:])
            return "".join(parts)
        parts.append(css[position : found.start()])
        replacement, position = _noise_step(css, found.group(), found.end())
        parts.append(replacement)
        if position < 0:
            return "".join(parts)
