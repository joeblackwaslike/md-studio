"""The deadline watchdog re-arms when the deadline is extended."""

from collections.abc import Callable
from typing import ClassVar

import pytest

from md_studio.readers.deadline import Deadline


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _FakeTimer:
    made: ClassVar[list["_FakeTimer"]] = []

    def __init__(self, interval: float, function: Callable[[], None]) -> None:
        self.interval = interval
        self.function = function
        self.daemon = False
        self.started = False
        self.cancelled = False
        self.made.append(self)

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True


class _Closer:
    def __init__(self) -> None:
        self.closed = 0

    def __call__(self) -> None:
        self.closed += 1


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr("md_studio.readers.deadline._clock", fake)
    _FakeTimer.made = []
    return fake


def test_firing_at_the_original_expiry_after_an_extension_does_not_close(clock: _Clock) -> None:
    deadline = Deadline(30)
    closer = _Closer()
    deadline.watch(closer, timer_factory=_FakeTimer)
    deadline.extend(15)

    clock.now = 1030
    _FakeTimer.made[0].function()

    assert closer.closed == 0
    assert not deadline.expired
    assert _FakeTimer.made[1].interval == pytest.approx(15)
    assert _FakeTimer.made[1].started


def test_firing_at_the_extended_expiry_closes(clock: _Clock) -> None:
    deadline = Deadline(30)
    closer = _Closer()
    deadline.watch(closer, timer_factory=_FakeTimer)
    deadline.extend(15)
    clock.now = 1030
    _FakeTimer.made[0].function()

    clock.now = 1045
    _FakeTimer.made[1].function()

    assert closer.closed == 1
    assert deadline.expired


def test_cancel_after_a_re_arm_prevents_a_late_close(clock: _Clock) -> None:
    deadline = Deadline(30)
    closer = _Closer()
    watchdog = deadline.watch(closer, timer_factory=_FakeTimer)
    deadline.extend(15)
    clock.now = 1030
    _FakeTimer.made[0].function()

    watchdog.cancel()
    clock.now = 1045
    _FakeTimer.made[1].function()

    assert _FakeTimer.made[1].cancelled
    assert closer.closed == 0
    assert not deadline.expired
