"""GitHub-style heading anchors."""

import unicodedata
from collections.abc import Iterable

_KEPT_MAJOR = frozenset("LMN")


def _kept(char: str) -> bool:
    category = unicodedata.category(char)
    return char in " -" or category[0] in _KEPT_MAJOR or category == "Pc"


def slugify(text: str) -> str:
    """Return the GitHub-style anchor for a heading's text."""
    return "".join(filter(_kept, text.lower())).replace(" ", "-")


def _unique(base: str, counts: dict[str, int]) -> str:
    slug = base
    while slug in counts:
        counts[base] = counts.get(base, 0) + 1
        slug = f"{base}-{counts[base]}"
    counts.setdefault(slug, 0)
    return slug


def github_slugs(headings: Iterable[str]) -> list[str]:
    """Return one anchor per heading in order, numbering repeats ``-1``, ``-2`` as GitHub does."""
    counts: dict[str, int] = {}
    return [_unique(slugify(heading), counts) for heading in headings]
