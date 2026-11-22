"""Markdown text escaping and backtick-fence escalation helpers."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_BACKTICK_RUN_RE = re.compile(r"`+")
_MIN_FENCE = 3
_BACKTICK = "`"
_DOLLAR = "$"
_ESCAPE_DOLLARS: ContextVar[bool] = ContextVar("escape_dollars", default=False)


@contextmanager
def dollar_escaping(*, enabled: bool) -> Iterator[None]:
    """Escape ``$`` in prose for the duration of the block when *enabled*."""
    token = _ESCAPE_DOLLARS.set(enabled)
    try:
        yield
    finally:
        _ESCAPE_DOLLARS.reset(token)


def escape_text(text: str) -> str:
    """Escape the few characters that would otherwise break inline Markdown.

    ``$`` is escaped too, but only inside :meth:`Renderer.render` of a math document.
    """
    escaped = text.replace("\\", r"\\").replace(_BACKTICK, r"\`")
    if _ESCAPE_DOLLARS.get():
        return escaped.replace(_DOLLAR, r"\$")
    return escaped


def _longest_backtick_run(text: str) -> int:
    """Return the length of the longest backtick run within *text*."""
    return max((len(run) for run in _BACKTICK_RUN_RE.findall(text)), default=0)


def code_span(text: str) -> str:
    """Render an inline code span with backtick-fence escalation."""
    longest = _longest_backtick_run(text)
    ticks = _BACKTICK * (longest + 1)
    needs_pad = bool(longest) or text.startswith(_BACKTICK) or text.endswith(_BACKTICK)
    pad = " " if needs_pad else ""
    return f"{ticks}{pad}{text}{pad}{ticks}"


def fence_for(code: str) -> str:
    """Return a backtick fence long enough to wrap *code*."""
    longest = _longest_backtick_run(code)
    return _BACKTICK * max(_MIN_FENCE, longest + 1)
