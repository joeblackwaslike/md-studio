"""Source readers that produce a core Document."""

from typing import Protocol

from md_studio.core.document import Document


class Reader(Protocol):
    """Turns a source path or URL into a :class:`Document`."""

    def __call__(self, source: str, /) -> Document:
        """Read *source* and return the parsed document."""
