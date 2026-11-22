"""Exceptions raised by the md_studio core pipeline."""


class MdStudioError(Exception):
    """Base exception for all md_studio errors."""


class ReadError(MdStudioError):
    """Raised when a source document cannot be opened or parsed."""


class FetchStatusError(ReadError):
    """Raised when a fetch ends in a non-success HTTP status."""

    def __init__(self, message: str, status: int) -> None:
        """Record the HTTP *status* alongside *message*."""
        self.status = status
        super().__init__(message)


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


class ExtensionLoadError(MdStudioError):
    """Raised when a requested Markdown extension is installed but failed to load."""

    def __init__(self, name: str, reason: str) -> None:
        """Record the extension name and the load failure text."""
        self.name = name
        self.reason = reason
        super().__init__(f"extension {name!r} failed to load: {reason}")
