"""URL helpers shared by the renderer and the extractors."""

import re
from urllib.parse import SplitResult, urlsplit

_CHARACTER_REFERENCE = re.compile(r"&(?=(?:#[0-9]+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);)")
_UNSAFE_DESTINATION = re.compile(r"[\s\x00-\x1f\x7f\\()<>]")


def safe_urlsplit(url: str) -> SplitResult | None:
    """Split *url*, or return ``None`` when it is malformed (for example ``http://[x``)."""
    try:
        return urlsplit(url)
    except ValueError:
        return None


def _percent(hit: re.Match[str]) -> str:
    return "".join(f"%{byte:02X}" for byte in hit.group().encode())


def encode_destination(url: str) -> str:
    r"""Percent-encode what could end or reshape a Markdown link destination.

    Whitespace (ASCII and Unicode), control characters, backslashes, parentheses and angle
    brackets are encoded as the percent form of their UTF-8 bytes, so a hostile URL cannot
    close the ``(...)`` or start a new line of Markdown. Existing ``%XX`` escapes are kept.
    The ampersand of anything shaped like a character reference (``&colon;``, ``&#58;``,
    ``&amp;``) is backslash-escaped so a Markdown reader keeps it as literal text instead of
    decoding it into another character; a plain ``&`` in a query string is left alone.
    """
    encoded = _UNSAFE_DESTINATION.sub(_percent, url)
    return _CHARACTER_REFERENCE.sub(lambda _hit: r"\&", encoded)
