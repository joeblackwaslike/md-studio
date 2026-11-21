"""Record and render which paragraphs an extension promoted to headings."""

from collections.abc import Sequence
from dataclasses import dataclass, field

_HEADER = (
    "# Heading promotions\n\n"
    "| Chapter | Text | Was | Classes | Level |\n"
    "| --- | --- | --- | --- | --- |\n"
)


_CELL_ESCAPES = str.maketrans({
    "\\": r"\\",
    "|": r"\|",
    "`": r"\`",
    "[": r"\[",
    "]": r"\]",
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
})


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


@dataclass(slots=True)
class AuditLog:
    """Mutable collector that extensions append promotions to via ``ExtCtx.audit``."""

    records: list[PromotionRecord] = field(default_factory=list)

    def add(self, record: PromotionRecord) -> None:
        """Append *record* to the log."""
        self.records.append(record)


def _cell(text: str) -> str:
    """Return *text* safe inside a table cell: one line, Markdown and HTML neutralised."""
    return " ".join(text.split()).translate(_CELL_ESCAPES)


def _row(record: PromotionRecord) -> str:
    """Render one promotion as a table row."""
    cells = (
        record.chapter,
        record.text,
        record.old_tag,
        " ".join(record.old_classes),
        str(record.level),
    )
    line = " | ".join(_cell(cell) for cell in cells)
    return f"| {line} |\n"


def render(records: Sequence[PromotionRecord]) -> str:
    """Render *records* as a Markdown report with one table row per promotion.

    Parameters
    ----------
    records:
        Promotions in document order.

    Returns
    -------
    str
        The Markdown report; pipes and newlines in cell text are escaped.
    """
    return _HEADER + "".join(_row(record) for record in records)
