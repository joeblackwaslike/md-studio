"""Render the YAML front-matter block and assemble it via the two-pass build.

The front matter sits above the body, so a chapter's file-absolute offset is its
body-relative offset plus the front-matter size. Because every numeric field is
right-aligned to a fixed width, the front matter's own size does not depend on
the offset values -- so a render with body-relative numbers measures the same
length as the final render with file-absolute numbers (asserted below).
"""

import re
from collections.abc import Mapping

from md_studio.core import ir
from md_studio.core.exceptions import MdStudioError
from md_studio.core.frontmatter.numbers import pad_number
from md_studio.core.frontmatter.ranges import (
    ChapterRange,
    absolute_ranges,
    preliminary_ranges,
)
from md_studio.core.frontmatter.yaml import yaml_inline_string, yaml_safe_string
from md_studio.core.render import ChapterOffset

_KEY_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_RESERVED_KEYS = (
    "title",
    "authors",
    "publisher",
    "published",
    "isbn",
    "language",
    "source_file",
    "chapters",
)

_YAML_NON_STRING_KEYS = ("on", "off", "yes", "no", "y", "n", "true", "false", "null")

ExtraProperties = Mapping[str, str | list[str]]


def _validate_extra_key(key: str) -> None:
    """Raise :class:`MdStudioError` when *key* is not a safe extra property key."""
    if not _KEY_PATTERN.fullmatch(key):
        msg = f"invalid front matter extra key {key!r}: must match [A-Za-z_][A-Za-z0-9_-]*"
        raise MdStudioError(msg)
    if key.lower() in _YAML_NON_STRING_KEYS:
        msg = f"invalid front matter extra key {key!r}: YAML reads it as a boolean or null"
        raise MdStudioError(msg)
    if key.lower() in _RESERVED_KEYS:
        msg = f"front matter extra key {key!r} collides with a reserved key"
        raise MdStudioError(msg)


def _extra_value_lines(key: str, entry: str | list[str]) -> list[str]:
    """Render one extra property as a scalar, an empty list, or a block list."""
    if isinstance(entry, str):
        return [f"{key}: {yaml_safe_string(entry)}"]
    if entry:
        return [f"{key}:", *(f"  - {yaml_safe_string(element)}" for element in entry)]
    return [f"{key}: []"]


def _extra_lines(extra: ExtraProperties | None) -> list[str]:
    """Validate and render caller-supplied extra properties."""
    lines: list[str] = []
    for key, entry in (extra or {}).items():
        _validate_extra_key(key)
        lines.extend(_extra_value_lines(key, entry))
    return lines


def _header(meta: ir.BookMeta) -> list[str]:
    """Render the book-level metadata lines."""
    lines = ["---", f"title: {yaml_inline_string(meta.title)}"]
    if meta.authors:
        joined = ", ".join(yaml_inline_string(author) for author in meta.authors)
        lines.append(f"authors: [{joined}]")
    if meta.publisher:
        lines.append(f"publisher: {yaml_inline_string(meta.publisher)}")
    if meta.published:
        lines.append(f"published: {yaml_inline_string(meta.published)}")
    if meta.isbn:
        lines.append(f"isbn: {yaml_safe_string(meta.isbn)}")
    if meta.language:
        lines.append(f"language: {yaml_inline_string(meta.language)}")
    if meta.source_file:
        lines.append(f"source_file: {yaml_inline_string(meta.source_file)}")
    return lines


def _chapter_lines(chapter: ChapterRange) -> list[str]:
    """Render one chapter entry's YAML lines."""
    lines = [
        f"  - title: {yaml_inline_string(chapter.title)}",
        f"    start_line: {pad_number(chapter.start_line, chapter.title)}",
        f"    end_line: {pad_number(chapter.end_line, chapter.title)}",
        f"    start_byte: {pad_number(chapter.start_byte, chapter.title)}",
        f"    end_byte: {pad_number(chapter.end_byte, chapter.title)}",
    ]
    if chapter.start_page is not None and chapter.end_page is not None:
        lines.extend([f"    start_page: {chapter.start_page}", f"    end_page: {chapter.end_page}"])
    return lines


def render(
    meta: ir.BookMeta,
    chapters: list[ChapterRange],
    *,
    extra: ExtraProperties | None = None,
) -> str:
    """Render the complete front-matter block (including trailing ``---``).

    *extra* properties follow the header fields and precede ``chapters:``; see
    :func:`build` for the key rules.
    """
    lines = _header(meta)
    lines.extend(_extra_lines(extra))
    lines.append("chapters:")
    for chapter in chapters:
        lines.extend(_chapter_lines(chapter))
    lines.append("---")
    return "{joined}\n".format(joined="\n".join(lines))


def build(
    meta: ir.BookMeta,
    titles: list[str],
    offsets: list[ChapterOffset],
    body: str,
    *,
    extra: ExtraProperties | None = None,
) -> tuple[str, list[ChapterRange]]:
    """Return the final front matter and file-absolute ranges (two-pass).

    Pass 1 renders with body-relative numbers to measure the front-matter size;
    pass 2 renders with file-absolute numbers. Fixed-width padding guarantees the
    two renders are byte-identical in length.

    Parameters
    ----------
    extra:
        Additional properties emitted after the header fields and before
        ``chapters:``, counted in pass 1 so chapter offsets stay correct. A
        ``str`` renders as a double-quoted scalar, a ``list[str]`` as a block
        list. Keys must match ``[A-Za-z_][A-Za-z0-9_-]*`` and must not be
        ``title``, ``authors``, ``publisher``, ``published``, ``isbn``,
        ``language``, ``source_file`` or ``chapters``, and must not be a YAML 1.1
        boolean or null word (``yes``, ``no``, ``on``, ``off``, ``y``, ``n``,
        ``true``, ``false``, ``null``, any case). An empty list renders as ``[]``.

    Raises
    ------
    MdStudioError
        When an extra key is invalid or collides with a reserved key.
    """
    preliminary = render(meta, preliminary_ranges(titles, offsets), extra=extra)
    ranges = absolute_ranges(
        titles,
        offsets,
        body,
        preliminary.count("\n"),
        len(preliminary.encode("utf-8")),
    )
    final = render(meta, ranges, extra=extra)
    if len(final) != len(preliminary):  # pragma: no cover - invariant guard
        msg = "front matter size changed between passes; padding width too small"
        raise MdStudioError(msg)
    return final, ranges
