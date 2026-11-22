"""Render image nodes: alt text, or an embed when the document asks for images."""

from md_studio.core import ir
from md_studio.core.render.escaping import escape_text
from md_studio.core.render.options import embeds_images
from md_studio.core.urls import encode_destination, safe_urlsplit

_EMBEDDABLE_SCHEMES = frozenset(("", "http", "https"))


def _bracket_text(text: str) -> str:
    escaped = escape_text(" ".join(text.split()))
    return escaped.replace("[", r"\[").replace("]", r"\]")


def _embeddable(src: str) -> bool:
    parts = safe_urlsplit(src)
    if parts is None or not src:
        return False
    scheme = parts.scheme.lower()
    return scheme in _EMBEDDABLE_SCHEMES and (bool(scheme) or not parts.netloc)


def render_image(node: ir.Image) -> str:
    """Render an image as its escaped alt text, or ``![alt](src)`` when images embed.

    When images embed, whitespace in the alt text is collapsed so it cannot start a new
    block. A source that is empty, malformed, protocol-relative, or has a scheme other than
    http(s) renders as the alt text alone, and any unsafe character in the source
    (whitespace, control characters, backslash, parentheses, angle brackets) is percent-encoded.
    """
    if not embeds_images():
        return escape_text(node.alt)
    src = node.src.strip()
    if not _embeddable(src):
        return _bracket_text(node.alt)
    return f"![{_bracket_text(node.alt)}]({encode_destination(src)})"
