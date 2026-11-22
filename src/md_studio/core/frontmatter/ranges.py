"""File-absolute chapter ranges within the rendered Markdown document."""

from dataclasses import dataclass

from md_studio.core.frontmatter.numbers import line_count
from md_studio.core.render import ChapterOffset


@dataclass(frozen=True, slots=True)
class ChapterRange:
    """File-absolute offsets describing where a chapter lives in the ``.md``."""

    title: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    start_page: int | None = None
    end_page: int | None = None


def _preliminary_range(title: str, offset: ChapterOffset) -> ChapterRange:
    """Build a single body-relative range (start == end) for one chapter."""
    first, last = offset.pages or (None, None)
    return ChapterRange(title, offset.line, offset.line, offset.byte, offset.byte, first, last)


def preliminary_ranges(
    titles: list[str],
    offsets: list[ChapterOffset],
) -> list[ChapterRange]:
    """Return body-relative ranges (start == end) used to size the front matter."""
    paired = zip(titles, offsets, strict=True)
    return [_preliminary_range(title, offset) for title, offset in paired]


def _spans(starts: list[int], total: int) -> list[tuple[int, int]]:
    """Pair each start with its end (one before the next; *total* for the last)."""
    if not starts:
        return []
    ends = [start - 1 for start in starts[1:]]
    ends.append(total)
    return list(zip(starts, ends, strict=True))


def _range(
    title: str,
    offset: ChapterOffset,
    line_span: tuple[int, int],
    byte_span: tuple[int, int],
) -> ChapterRange:
    """Build the file-absolute range for one chapter from its line and byte spans."""
    first, last = offset.pages or (None, None)
    return ChapterRange(title, *line_span, *byte_span, first, last)


def absolute_ranges(
    titles: list[str],
    offsets: list[ChapterOffset],
    body: str,
    front_matter_lines: int,
    front_matter_bytes: int,
) -> list[ChapterRange]:
    """Compute file-absolute chapter ranges from body-relative start offsets."""
    lines = _spans(
        [offset.line + front_matter_lines for offset in offsets],
        front_matter_lines + line_count(body),
    )
    bytes_ = _spans(
        [offset.byte + front_matter_bytes for offset in offsets],
        front_matter_bytes + len(body.encode("utf-8")) - 1,
    )
    paired = zip(titles, offsets, lines, bytes_, strict=True)
    return [_range(*fields) for fields in paired]
