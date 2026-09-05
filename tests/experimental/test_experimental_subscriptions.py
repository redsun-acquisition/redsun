"""Tests for a slot subscribed to an ophyd-async device signal."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from ophyd_async.core import soft_signal_r_and_setter

from redsun.experimental import AsPresenter, Session, WiringError, slot

if TYPE_CHECKING:
    from collections.abc import Callable

    from ophyd_async.core import SignalR

    from .conftest import BuildSession


class Watcher:
    """Presenter whose slot records every reading it is handed."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.seen: list[float] = []

    @slot
    def on_reading(self, reading: dict[str, Any]) -> None:
        self.seen.append(next(iter(reading.values()))["value"])

    def unmarked(self, reading: dict[str, Any]) -> None:
        """Take a reading, without being marked as connectable."""


class Renamed:
    """Presenter whose port is addressed by a name of its own."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.seen: list[float] = []

    @slot(name="readings")
    def on_reading(self, reading: dict[str, Any]) -> None:
        self.seen.append(next(iter(reading.values()))["value"])


class App(Session):
    config: ClassVar[dict[str, Any]] = {"name": "subscribing"}

    watcher: AsPresenter[Watcher]
    renamed: AsPresenter[Renamed]


@pytest.fixture
def counter() -> tuple[SignalR[int], Callable[[int], None]]:
    """Return a connected soft signal and the setter that drives it."""
    signal, setter = soft_signal_r_and_setter(int, initial_value=0, name="counter")
    return signal, setter


def test_a_reading_reaches_the_slot(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    """Subscribing delivers the reading the device already holds, then the rest.

    So a component starts from the current value rather than from nothing, and
    does not have to wait for the next change to know where things stand.
    """
    signal, setter = counter
    session = build(App)
    session.subscribe(signal, session.watcher.on_reading)

    setter(42)

    assert session.watcher.seen == [0, 42]


def test_the_subscription_is_recorded_by_both_ends(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    signal, _ = counter
    session = build(App)

    record = session.subscribe(signal, session.watcher.on_reading)

    assert (record.source, record.consumer, record.consumer_port) == (
        "counter",
        "watcher",
        "on_reading",
    )
    assert session.subscriptions == [record]


def test_the_record_uses_the_port_name_the_slot_declares(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    """A configuration addresses the port, so the record must name it too."""
    signal, _ = counter
    session = build(App)

    record = session.subscribe(signal, session.renamed.on_reading)

    assert record.consumer_port == "readings"


def test_a_slot_that_is_not_marked_is_refused(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    signal, _ = counter
    session = build(App)

    with pytest.raises(WiringError, match="unmarked"):
        session.subscribe(signal, session.watcher.unmarked)


def test_shutdown_stops_the_readings(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    """A reading delivered after teardown reaches a component being finalized."""
    signal, setter = counter
    session = build(App)
    watcher = session.watcher
    session.subscribe(signal, watcher.on_reading)
    setter(1)

    session.shutdown()
    setter(2)

    assert watcher.seen == [0, 1]


def test_shutdown_forgets_the_subscriptions(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    signal, _ = counter
    session = build(App)
    session.subscribe(signal, session.watcher.on_reading)

    session.shutdown()

    assert session.subscriptions == []


def test_a_subscribed_port_is_not_reported_as_unconnected(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    """A subscription is a connection, so the wiring report counts it as one."""
    signal, _ = counter
    session = build(App)
    assert "watcher.on_reading" in session.unconnected.slots

    session.subscribe(signal, session.watcher.on_reading)

    assert "watcher.on_reading" not in session.unconnected.slots
