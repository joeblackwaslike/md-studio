"""Pick a text encoding for raw HTML bytes."""

import codecs

from md_studio.readers.charset import meta_charset

_BOMS = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)
_CP_ALIASES = frozenset(
    (
        "iso-8859-1",
        "iso8859-1",
        "iso_8859-1",
        "latin1",
        "latin-1",
        "l1",
        "us-ascii",
        "ascii",
        "cp1252",
        "x-cp1252",
        "windows-1252",
    ),
)
_NOT_HTML_CODECS = frozenset(
    ("undefined", "unicode-escape", "raw-unicode-escape", "punycode", "idna"),
)


def _codec_name(label: str) -> str:
    cleaned = label.strip().lower()
    return "cp1252" if cleaned in _CP_ALIASES else cleaned


def _is_text_codec(name: str) -> bool:
    try:
        codec = codecs.lookup(name)
    except LookupError:
        return False
    is_text = getattr(codec, "_is_text_encoding", True)
    return bool(is_text) and codec.name not in _NOT_HTML_CODECS


def _decode_as(raw: bytes, label: str) -> str | None:
    name = _codec_name(label)
    if not _is_text_codec(name):
        return None
    try:
        return raw.decode(name)
    except UnicodeError:
        return None


def decode_html(raw: bytes, charset: str | None) -> str | None:
    """Return *raw* as text, or ``None`` to let lxml guess.

    Order is BOM, HTTP charset, a real ``<meta>`` charset, then strict UTF-8. HTML's
    latin-1 and ASCII labels decode as Windows-1252.
    """
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            return _decode_as(raw, encoding)
    for label in (charset, meta_charset(raw)):
        text = _decode_as(raw, label) if label else None
        if text is not None:
            return text
    return _decode_as(raw, "utf-8")
