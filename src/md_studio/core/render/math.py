"""Render TeX math to ``$`` and ``$$`` Markdown spans that always close."""

import re

_UNESCAPED_DOLLAR_RE = re.compile(r"(?<!\\)((?:\\\\)*)\$")
_ODD_BACKSLASH_TAIL_RE = re.compile(r"(?<!\\)(?:\\\\)*\\$")
_NEWLINE_RE = re.compile(r"[\r\n]")
_ESCAPED_DOLLAR = r"\1\$"


def _safe_body(tex: str) -> str:
    """Escape unescaped dollars and keep a trailing backslash from escaping the closer."""
    body = _UNESCAPED_DOLLAR_RE.sub(_ESCAPED_DOLLAR, tex)
    return f"{body} " if _ODD_BACKSLASH_TAIL_RE.search(body) else body


def inline_math(tex: str) -> str:
    r"""Render ``$tex$``; blank *tex* renders nothing.

    Line breaks become spaces and surrounding whitespace is stripped. Every unescaped
    ``$`` is escaped: ``\$`` stays as written, while in ``\\$`` the backslashes are an
    escaped backslash, so that dollar is escaped too. A trailing odd run of backslashes
    gets one space so the closing ``$`` is not escaped.
    """
    flat = _NEWLINE_RE.sub(" ", tex).strip()
    return f"${_safe_body(flat)}$" if flat else ""


def block_math(tex: str) -> str:
    """Render ``$$`` fenced display math; blank *tex* renders nothing.

    Blank lines are dropped (they would end the block), surrounding whitespace is
    stripped, and dollars and trailing backslashes are handled as in :func:`inline_math`.
    """
    lines = [line.strip() for line in tex.splitlines() if line.strip()]
    return f"$$\n{_safe_body(chr(10).join(lines))}\n$$" if lines else ""
