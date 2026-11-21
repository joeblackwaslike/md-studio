"""Assemble parsed EPUB chapters into the render-ready IR."""
# flake8: noqa: WPS412 -- this package __init__ is a pure public-API re-export surface

from md_studio.core.assemble.mapping import assemble

__all__ = ["assemble"]
