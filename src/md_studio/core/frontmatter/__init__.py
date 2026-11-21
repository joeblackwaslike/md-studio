"""Build the YAML front matter with per-chapter line and byte offsets."""
# flake8: noqa: WPS412 -- this package __init__ is a pure public-API re-export surface

from md_studio.core.frontmatter.document import build, render
from md_studio.core.frontmatter.numbers import NUMERIC_WIDTH, pad_number
from md_studio.core.frontmatter.ranges import ChapterRange
from md_studio.core.frontmatter.yaml import yaml_inline_string

__all__ = [
    "NUMERIC_WIDTH",
    "ChapterRange",
    "build",
    "pad_number",
    "render",
    "yaml_inline_string",
]
