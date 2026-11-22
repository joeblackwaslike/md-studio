"""Pick a text encoding for raw HTML bytes."""

import codecs
import re

_BOMS = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)
_META_CHARSET = re.compile(rb"<meta\s[^>]*?\bcharset\s*=\s*[\"']?[\w-]+", re.IGNORECASE)
_NOT_HTML_CODECS = frozenset(
    ("undefined", "unicode-escape", "raw-unicode-escape", "punycode", "idna"),
)
_META_WINDOW = 4096


def _is_text_codec(name: str) -> bool:
    try:
        codec = codecs.lookup(name)
    except LookupError:
        return False
    is_text = getattr(codec, "_is_text_encoding", True)
    return bool(is_text) and codec.name not in _NOT_HTML_CODECS


def _decode_as(raw: bytes, encoding: str) -> str | None:
    if not _is_text_codec(encoding):
        return None
    try:
        return raw.decode(encoding)
    except UnicodeError:
        return None


def decode_html(raw: bytes, charset: str | None) -> str | None:
    """Return *raw* as text, or ``None`` to let lxml guess.

    Order is BOM, then HTTP charset, then strict UTF-8 unless a ``<meta>`` charset decides.
    """
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            return _decode_as(raw, encoding)
    declared = _decode_as(raw, charset) if charset else None
    if declared is not None or _META_CHARSET.search(raw[:_META_WINDOW]):
        return declared
    return _decode_as(raw, "utf-8")
