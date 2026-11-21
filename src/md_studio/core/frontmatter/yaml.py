"""Minimal YAML scalar quoting for front-matter values (parity with safaribooks).

Known limitations, kept so output stays byte-identical to the baseline and tracked
in issue #1: a value containing a newline is wrapped in double quotes without the
newline being escaped, so it is not a single-line scalar; and values that YAML reads
as another type when bare (``true``, ``null``, ``123``) are emitted unquoted.
"""

_NEEDS_QUOTING = frozenset(":#'\"\n[]{},*&!|>%@`")


def yaml_inline_string(raw: str) -> str:
    """Quote *raw* for safe single-line YAML output."""
    if _needs_quoting(raw):
        escaped = raw.replace("\\", r"\\").replace('"', r"\"")
        return f'"{escaped}"'
    return raw


def _needs_quoting(raw: str) -> bool:
    """Return ``True`` when *raw* cannot be emitted as a bare YAML scalar."""
    if not raw or raw != raw.strip():
        return True
    return any(token in raw for token in _NEEDS_QUOTING)
