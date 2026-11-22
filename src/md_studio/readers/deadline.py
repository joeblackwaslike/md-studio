"""A wall-clock budget shared by every phase of one fetch."""

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol

from md_studio.core.exceptions import ReadError

DEADLINE_SECONDS = 30.0
_clock = time.monotonic
MESSAGE = "Fetch exceeded the total deadline"


_active: ContextVar["Deadline | None"] = ContextVar("active_deadline", default=None)


class _TimerLike(Protocol):
    daemon: bool

    def start(self) -> None: ...

    def cancel(self) -> None: ...


type TimerFactory = Callable[[float, Callable[[], None]], _TimerLike]


class _Watchdog:
    """Calls a function when a deadline passes, re-arming itself if the deadline was extended."""

    def __init__(
        self, deadline: "Deadline", close: Callable[[], None], timer_factory: TimerFactory
    ) -> None:
        self._deadline = deadline
        self._close = close
        self._timer_factory = timer_factory
        self._lock = threading.Lock()
        self._cancelled = False
        self._timer = self._arm()

    def cancel(self) -> None:
        """Stop the watchdog for good."""
        with self._lock:
            self._cancelled = True
            self._timer.cancel()

    def _arm(self) -> _TimerLike:
        timer = self._timer_factory(self._deadline.remaining(), self._fire)
        timer.daemon = True
        timer.start()
        return timer

    def _fire(self) -> None:
        with self._lock:
            if self._cancelled:
                return
            if self._deadline.remaining() > 0:
                self._timer = self._arm()
                return
        self._deadline.expired = True
        self._close()


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

    def extend(self, seconds: float) -> None:
        """Add *seconds* of budget, for time that must not count against the fetch."""
        self._expires += seconds

    @contextmanager
    def activate(self) -> Iterator[None]:
        """Make this the deadline that :func:`extend_active` extends within the block."""
        token = _active.set(self)
        try:
            yield
        finally:
            _active.reset(token)

    def watch(
        self, close: Callable[[], None], *, timer_factory: TimerFactory = threading.Timer
    ) -> _Watchdog:
        """Start a daemon watchdog that flags expiry and calls *close* when time runs out.

        *timer_factory* builds the timers (``threading.Timer`` by default); tests inject a
        controllable one.
        """
        return _Watchdog(self, close, timer_factory)


def extend_active(seconds: float) -> None:
    """Extend the deadline active in this context, if any, by a pause that is not fetch time."""
    deadline = _active.get()
    if deadline is not None:
        deadline.extend(seconds)
