"""Render inline IR nodes to GitHub-Flavored Markdown."""

from collections.abc import Callable
from dataclasses import replace
from types import MappingProxyType

from md_studio.core import ir
from md_studio.core.render import images, leaves
from md_studio.core.urls import encode_destination

Inlines = tuple[ir.Inline, ...]

_LEAF_RENDERERS: MappingProxyType[type, Callable[..., str]] = MappingProxyType({
    ir.Text: leaves.render_text,
    ir.CodeSpan: leaves.render_code_span,
    ir.Image: images.render_image,
    ir.Math: leaves.render_math,
    ir.LineBreak: leaves.render_line_break,
    ir.FootnoteRef: leaves.render_footnote_ref,
})

_STRIKE = "~~"
_WRAPPERS: MappingProxyType[type, tuple[str, str]] = MappingProxyType({
    ir.Emphasis: ("*", "*"),
    ir.Strong: ("**", "**"),
    ir.Strikethrough: (_STRIKE, _STRIKE),
})


def render_inlines(nodes: Inlines) -> str:
    """Render an inline sequence to a Markdown string."""
    return "".join(_render_inline(node) for node in nodes)


def _render_inline(node: ir.Inline) -> str:
    """Render a single inline node to Markdown."""
    leaf = _LEAF_RENDERERS.get(type(node))
    if leaf is not None:
        return leaf(node)
    if isinstance(node, ir.Link):
        return f"[{render_inlines(node.children)}]({encode_destination(node.href)})"
    if isinstance(node, ir.Strikethrough):
        return _render_strikethrough(node)
    if isinstance(node, (ir.Emphasis, ir.Strong)):
        prefix, suffix = _WRAPPERS[type(node)]
        return f"{prefix}{render_inlines(node.children)}{suffix}"
    return ""


def _without_strikethrough(nodes: Inlines) -> Inlines:
    """Return *nodes* with every nested strikethrough replaced by its own content."""
    flat: list[ir.Inline] = []
    for node in nodes:
        if isinstance(node, ir.Strikethrough):
            flat.extend(_without_strikethrough(node.children))
        elif isinstance(node, (ir.Emphasis, ir.Strong, ir.Link)):
            flat.append(replace(node, children=_without_strikethrough(node.children)))
        else:
            flat.append(node)
    return tuple(flat)


def _render_strikethrough(node: ir.Strikethrough) -> str:
    """Render ``~~content~~`` with the content's edge whitespace moved outside the tildes.

    GFM does not strike text whose delimiters touch whitespace on the inside. Content that
    is only whitespace renders as that whitespace, and a strikethrough inside another is
    flattened so the outer one covers it.
    """
    inner = render_inlines(_without_strikethrough(node.children))
    core = inner.strip()
    if not core:
        return inner
    lead = inner[: len(inner) - len(inner.lstrip())]
    trail = inner[len(inner.rstrip()) :]
    return f"{lead}{_STRIKE}{core}{_STRIKE}{trail}"
