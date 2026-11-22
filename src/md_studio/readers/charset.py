"""Find a charset declared by a real ``<meta>`` tag near the top of an HTML document."""

import re

_WINDOW = 4096
_COMMENT = re.compile(rb"<!--.*?(?:-->|\Z)", re.DOTALL)
_META_TAG = re.compile(rb"<meta(?=[\s/>])([^>]*)>", re.IGNORECASE)
_ATTRIBUTE = re.compile(rb"([^\s\"'=/>]+)(?:\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>]+)))?")
_CONTENT_CHARSET = re.compile(rb"charset\s*=\s*[\"']?\s*([\w.:-]+)", re.IGNORECASE)


def _attributes(tag: bytes) -> dict[bytes, bytes]:
    found: dict[bytes, bytes] = {}
    for name, double, single, bare in _ATTRIBUTE.findall(tag):
        found.setdefault(name.lower(), double or single or bare)
    return found


def _label(attrs: dict[bytes, bytes]) -> bytes | None:
    direct = attrs.get(b"charset", b"").strip()
    if direct:
        return direct
    if attrs.get(b"http-equiv", b"").strip().lower() != b"content-type":
        return None
    match = _CONTENT_CHARSET.search(attrs.get(b"content", b""))
    return match.group(1) if match else None


def meta_charset(raw: bytes) -> str | None:
    """Return the charset label of the first real ``<meta>`` declaration, if any.

    Comments are removed first, attribute values are parsed rather than searched, and
    names like ``data-charset`` do not count.
    """
    head = _COMMENT.sub(b"", raw[:_WINDOW])
    for tag in _META_TAG.findall(head):
        label = _label(_attributes(tag))
        if label:
            return label.decode("ascii", errors="ignore")
    return None
