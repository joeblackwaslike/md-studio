"""Map a heading's text to a level using the titles of a PDF's outline."""

import re
from collections.abc import Mapping, Sequence

_MAX_LEVEL = 6
_NUMBERING = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[A-Z]\.\d+(?:\.\d+)*)\s+")


def outline_key(title: str) -> str:
    """Return *title* normalized for matching: spacing, case and a leading section number removed."""
    plain = " ".join(title.split())
    return _NUMBERING.sub("", plain, count=1).casefold()


def heading_level(text: str, outline: Mapping[str, int]) -> int:
    """Return the level of heading *text*: its outline depth, or one below the deepest entry.

    *outline* maps :func:`outline_key` titles to 1-based depth. Without an outline every
    heading is level 1.
    """
    if not outline:
        return 1
    unlisted = max(outline.values()) + 1
    return min(outline.get(outline_key(text), unlisted), _MAX_LEVEL)


def leading_unmatched(texts: Sequence[str], outline: Mapping[str, int]) -> int:
    """Return how many headings come before the first one that matches *outline*.

    These are the title, abstract and similar front headings; the reader gives them level 1
    so they start their own chapters. Zero without an outline or when nothing matches.
    """
    for position, text in enumerate(texts):
        if outline_key(text) in outline:
            return position
    return 0
