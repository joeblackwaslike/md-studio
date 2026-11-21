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


_ESCAPE_PAIRS = (
    ("\\", r"\\"),
    ('"', r"\""),
    ("\n", r"\n"),
    ("\r", r"\r"),
    ("\t", r"\t"),
)
_ESCAPES = str.maketrans(dict(_ESCAPE_PAIRS))
_SHORT_HEX = 0xFF
_MEDIUM_HEX = 0xFFFF


def yaml_safe_string(raw: str) -> str:
    """Return *raw* as a double-quoted YAML scalar that round-trips exactly.

    Backslash, double quote, newline, carriage return, tab and every
    non-printable character are escaped, so any ``str`` parses back unchanged.
    """
    escaped = "".join(_escape_char(char) for char in raw.translate(_ESCAPES))
    return f'"{escaped}"'


def _escape_char(char: str) -> str:
    """Escape one non-printable character; printable ones pass through."""
    if char.isprintable():
        return char
    code = ord(char)
    if code <= _SHORT_HEX:
        return f"\\x{code:02x}"
    if code <= _MEDIUM_HEX:
        return f"\\u{code:04x}"
    return f"\\U{code:08x}"
