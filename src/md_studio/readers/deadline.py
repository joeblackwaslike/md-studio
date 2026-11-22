"""A wall-clock budget shared by every phase of one fetch."""

import threading
import time
from collections.abc import Callable

from md_studio.core.exceptions import ReadError

DEADLINE_SECONDS = 30.0
_clock = time.monotonic
MESSAGE = "Fetch exceeded the total deadline"


class Deadline:
    """Total time allowed for a fetch, from construction onward."""

    def __init__(self, seconds: float | None = None) -> None:
        """Start the clock with *seconds* of budget (default ``DEADLINE_SECONDS``)."""
        budget = DEADLINE_SECONDS if seconds is None else seconds
        self._expires = _clock() + budget
        self.expired = False

    def remaining(self) -> float:
        """Return the seconds left, never negative."""
        return max(self._expires - _clock(), 0)

    def check(self) -> None:
        """Raise :class:`ReadError` when the budget is spent."""
        self.require()

    def require(self) -> float:
        """Return the seconds left from a single clock read, or raise when none remain."""
        left = self.remaining()
        if left <= 0:
            raise ReadError(MESSAGE)
        return left

    def watch(self, close: Callable[[], None]) -> threading.Timer:
        """Start a daemon timer that flags expiry and calls *close* when time runs out."""
        timer = threading.Timer(self.remaining(), self._fire, args=(close,))
        timer.daemon = True
        timer.start()
        return timer

    def _fire(self, close: Callable[[], None]) -> None:
        self.expired = True
        close()
