"""A wall-clock budget shared by every phase of one fetch."""

import time

from md_studio.core.exceptions import ReadError

DEADLINE_SECONDS = 30.0
_clock = time.monotonic


class Deadline:
    """Total time allowed for a fetch, from construction onward."""

    def __init__(self, seconds: float = DEADLINE_SECONDS) -> None:
        """Start the clock with *seconds* of budget."""
        self._expires = _clock() + seconds

    def remaining(self) -> float:
        """Return the seconds left, which is zero or negative once expired."""
        return self._expires - _clock()

    def check(self) -> None:
        """Raise :class:`ReadError` when the budget is spent."""
        if self.remaining() <= 0:
            raise ReadError("Fetch exceeded the total deadline")
