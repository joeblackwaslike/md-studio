"""Output sinks that persist rendered Markdown."""

from pathlib import Path
from typing import Protocol

from md_studio.core.convert import RenderedMarkdown


class Sink(Protocol):
    """Destination for rendered Markdown."""

    def write(self, rendered: RenderedMarkdown, *, name: str) -> Path:
        """Persist *rendered* and return where it was written.

        Parameters
        ----------
        rendered:
            The converted Markdown.
        name:
            Logical name of the document, for sinks that derive a location from it.
        """
        ...
