"""Record and render which paragraphs an extension promoted to headings."""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

_HEADER = (
    "# Heading promotions\n\n"
    "| Chapter | Text | Was | Classes | Level |\n"
    "| --- | --- | --- | --- | --- |\n"
)
_category = unicodedata.category
_MAX_CELL_CHARS = 200
_CUT_AT = _MAX_CELL_CHARS - 1
_INVISIBLE = frozenset(("Cc", "Cf"))
_ESCAPED_PIPE = r"\|"


@dataclass(frozen=True, slots=True)
class PromotionRecord:
    """One paragraph promoted to a heading.

    ``level`` is the source heading level (1 for ``<h1>``), before the renderer demotes
    headings under the chapter title.
    """

    chapter: str
    text: str
    old_tag: str
    old_classes: tuple[str, ...]
    level: int


def _visible(text: str) -> str:
    """Return *text* without control or format characters, backticks, or extra whitespace."""
    spaced = "".join(" " if char.isspace() else char for char in text)
    kept = "".join(char for char in spaced if _category(char) not in _INVISIBLE)
    return " ".join(kept.replace("`", "").split())


def _cell(text: str) -> str:
    """Return *text* as an inline code span that is inert in a Markdown table.

    The text is untrusted. Whitespace is collapsed, control and format characters
    (including bidi overrides) are dropped, backticks are removed, the length is capped,
    and pipes are escaped. A code span cannot turn into a link, emphasis or HTML.
    """
    shown = _visible(text)
    if len(shown) > _MAX_CELL_CHARS:
        shown = "".join((shown[:_CUT_AT], "…"))
    return f"`{shown.replace('|', _ESCAPED_PIPE)}`" if shown else ""


def _row(record: PromotionRecord) -> str:
    """Render one promotion as a table row."""
    cells = (
        record.chapter,
        record.text,
        record.old_tag,
        " ".join(record.old_classes),
    )
    line = " | ".join(_cell(cell) for cell in cells)
    return f"| {line} | {record.level} |\n"


def render(records: Sequence[PromotionRecord]) -> str:
    """Render *records* as a Markdown report with one table row per promotion.

    Parameters
    ----------
    records:
        Promotions in document order.

    Returns
    -------
    str
        The Markdown report. Every text cell is an inline code span with control
        characters and backticks removed and pipes escaped, so untrusted EPUB text cannot
        inject links, emphasis, HTML or bidi tricks.
    """
    return _HEADER + "".join(_row(record) for record in records)
