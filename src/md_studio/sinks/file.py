"""Sink that writes Markdown to a single file."""

from pathlib import Path

from md_studio.core.convert import RenderedMarkdown


class FileSink:
    """Write rendered Markdown to a fixed destination path."""

    def __init__(self, dest: Path, *, force: bool = False) -> None:
        """Configure the destination and whether an existing file may be replaced."""
        self._dest = dest
        self._force = force

    def write(self, rendered: RenderedMarkdown, *, name: str) -> Path:
        """Write ``rendered.text`` as UTF-8 to the destination, creating parent directories.

        Parameters
        ----------
        rendered:
            The converted Markdown.
        name:
            Accepted for the ``Sink`` protocol; unused.

        Returns
        -------
        Path
            The written file path.

        Raises
        ------
        FileExistsError
            When the destination exists and ``force`` is false.
        """
        if self._dest.exists() and not self._force:
            msg = f"Refusing to overwrite existing file: {self._dest}"
            raise FileExistsError(msg)
        self._dest.parent.mkdir(parents=True, exist_ok=True)
        self._dest.write_text(rendered.text, encoding="utf-8")
        return self._dest
