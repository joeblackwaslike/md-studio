"""Source-level fixes: transform the parsed document before extraction.

A fix is registered exactly like a :class:`MarkdownExtension` (built-in table or the
``md_studio.extensions`` entry-point group) and enabled by the same ``--ext`` name, but
it implements ``apply`` instead of the IR hooks and runs before extraction, in listed
order. Names are shared with Markdown extensions, so they must be unique across both.
"""

from typing import ClassVar, Protocol

from md_studio.core.document import Document


class SourceFix(Protocol):
    """A named transformation of a :class:`Document` run before IR extraction."""

    name: ClassVar[str]

    def apply(self, document: Document) -> Document:
        """Return the fixed *document*; must not mutate the input."""
        ...
