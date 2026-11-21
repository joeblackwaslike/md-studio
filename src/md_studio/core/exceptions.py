"""Exceptions raised by the md_studio core pipeline."""


class MdStudioError(Exception):
    """Base exception for all md_studio errors."""


class ReadError(MdStudioError):
    """Raised when a source document cannot be opened or parsed."""


class OffsetOverflowError(MdStudioError):
    """Raised when a chapter offset exceeds the fixed front-matter field width."""

    def __init__(self, chapter: str, offset: int, width: int) -> None:
        """Record the offending chapter, offset, and field width."""
        self.chapter = chapter
        self.offset = offset
        self.width = width
        super().__init__(
            f"Offset {offset} for chapter {chapter!r} exceeds {width}-digit field width",
        )


class UnknownExtensionError(MdStudioError):
    """Raised when a configured Markdown extension name is not registered."""

    def __init__(self, name: str, available: list[str]) -> None:
        """Record the unknown name and the list of available extensions."""
        self.name = name
        self.available = available
        joined = ", ".join(available) or "(none)"
        super().__init__(f"Unknown markdown extension {name!r}; available: {joined}")
