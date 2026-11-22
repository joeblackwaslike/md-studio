"""Per-document rendering switches, held in one context variable for the length of a render."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Per-document rendering switches, in force for the duration of one render."""

    escape_dollars: bool = False
    embed_images: bool = False


_OPTIONS: ContextVar[RenderOptions | None] = ContextVar("render_options", default=None)
_PLAIN = RenderOptions()


@contextmanager
def render_options(*, escape_dollars: bool, embed_images: bool) -> Iterator[None]:
    """Apply the document's render switches for the duration of the block."""
    token = _OPTIONS.set(RenderOptions(escape_dollars, embed_images))
    try:
        yield
    finally:
        _OPTIONS.reset(token)


def current_options() -> RenderOptions:
    """Return the switches of the render in progress, or the plain defaults outside one."""
    return _OPTIONS.get() or _PLAIN


def embeds_images() -> bool:
    """Return whether images render as ``![alt](src)`` instead of their alt text."""
    return current_options().embed_images
