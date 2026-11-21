"""Serialize the Markdown IR to GFM while tracking per-chapter offsets."""
# flake8: noqa: WPS412 -- this package __init__ is a pure public-API re-export surface

from md_studio.core.render.inlines import render_inlines
from md_studio.core.render.offsets import ChapterOffset, RenderResult
from md_studio.core.render.renderer import Renderer

__all__ = [
    "ChapterOffset",
    "RenderResult",
    "Renderer",
    "render_inlines",
]
