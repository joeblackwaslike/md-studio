"""Simple block-level IR nodes (paragraph, heading, code, rule)."""

from dataclasses import dataclass, field

from md_studio.core.ir.meta import Meta
from md_studio.core.ir.references import Inline


@dataclass(frozen=True, slots=True)
class Paragraph:
    """A paragraph of inline content."""

    children: tuple[Inline, ...]
    meta: Meta = field(default_factory=Meta)


@dataclass(frozen=True, slots=True)
class Heading:
    """A heading at ``level`` 1-6."""

    level: int
    children: tuple[Inline, ...]
    meta: Meta = field(default_factory=Meta)


@dataclass(frozen=True, slots=True)
class CodeBlock:
    """A fenced code block."""

    code: str
    language: str = ""


@dataclass(frozen=True, slots=True)
class MathBlock:
    """Display TeX math, rendered as a ``$$`` fenced block and never escaped."""

    tex: str


@dataclass(frozen=True, slots=True)
class HorizontalRule:
    """A thematic break (``<hr/>``)."""
