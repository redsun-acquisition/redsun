"""Tests for a slot subscribed to an ophyd-async device signal."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from ophyd_async.core import (
    StandardReadable,
    soft_signal_r_and_setter,
    soft_signal_rw,
)

from redsun import AsDevice, AsPresenter, Session, WiringError, slot

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from ophyd_async.core import SignalR

    from redsun import Link

    from .conftest import BuildSession


class Watcher:
    """Presenter whose slot records every reading it is handed."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.seen: list[float] = []

    @slot
    def on_reading(self, reading: dict[str, Any]) -> None:
        self.seen.append(next(iter(reading.values()))["value"])

    def unmarked(self, reading: dict[str, Any]) -> None:
        """Take a reading, without being marked as connectable."""


class Renamed:
    """Presenter whose port is addressed by a name of its own."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.seen: list[float] = []

    @slot(name="readings")
    def on_reading(self, reading: dict[str, Any]) -> None:
        self.seen.append(next(iter(reading.values()))["value"])


class Stage(StandardReadable):
    def __init__(self, name: str) -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, initial_value=1.5)
        super().__init__(name=name)


class App(Session):
    config: ClassVar[dict[str, Any]] = {"session": "subscribing"}

    watcher: AsPresenter[Watcher]
    renamed: AsPresenter[Renamed]


class Following(App):
    stage: AsDevice[Stage]

    def wire(self) -> Iterator[Link]:
        yield self.stage.position, self.watcher.on_reading


@pytest.fixture
def counter() -> tuple[SignalR[int], Callable[[int], None]]:
    """Return a connected soft signal and the setter that drives it."""
    signal, setter = soft_signal_r_and_setter(int, initial_value=0, name="counter")
    return signal, setter


def test_a_reading_reaches_the_slot(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    """Deliver a signal's current reading to a subscribed slot, then each change."""
    signal, setter = counter

    class Wired(App):
        def wire(self) -> Iterator[Link]:
            yield signal, self.watcher.on_reading

    session = build(Wired)
    setter(42)

    assert session.watcher.seen == [0, 42]


def test_the_subscription_is_recorded_by_both_ends(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    """Record a subscription with the signal as publisher and the slot as consumer."""
    signal, _ = counter

    class Wired(App):
        def wire(self) -> Iterator[Link]:
            yield signal, self.watcher.on_reading

    session = build(Wired)

    [link] = session.connections

    assert (link.publisher_port, link.consumer, link.consumer_port) == (
        "counter",
        "watcher",
        "on_reading",
    )


def test_a_signal_of_a_device_is_recorded_under_the_device(
    build: BuildSession,
) -> None:
    """Record the subscription of a device signal under the device's name."""
    session = build(Following)

    assert [str(link) for link in session.connections] == [
        "stage.position -> watcher.on_reading"
    ]
    assert session.watcher.seen == [1.5]


def test_the_record_uses_the_port_name_the_slot_declares(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    """Record a subscription under the port name the slot declares."""
    signal, _ = counter

    class Wired(App):
        def wire(self) -> Iterator[Link]:
            yield signal, self.renamed.on_reading

    session = build(Wired)

    assert session.connections[0].consumer_port == "readings"


def test_a_slot_that_is_not_marked_is_refused(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    """Refuse to subscribe a method not marked as a slot."""
    signal, _ = counter

    class Wired(App):
        def wire(self) -> Iterator[Link]:
            yield signal, self.watcher.unmarked

    with pytest.raises(WiringError, match="unmarked"):
        build(Wired)


def test_shutdown_stops_the_readings(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    """Stop delivering readings to a slot once the session shuts down."""
    signal, setter = counter

    class Wired(App):
        def wire(self) -> Iterator[Link]:
            yield signal, self.watcher.on_reading

    session = build(Wired)
    watcher = session.watcher
    setter(1)

    session.shutdown()
    setter(2)

    assert watcher.seen == [0, 1]


def test_shutdown_forgets_the_subscriptions(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    """Forget the subscriptions when the session shuts down."""
    signal, _ = counter

    class Wired(App):
        def wire(self) -> Iterator[Link]:
            yield signal, self.watcher.on_reading

    session = build(Wired)
    session.shutdown()

    assert session.connections == []


def test_a_subscribed_port_is_not_reported_as_unconnected(
    counter: tuple[SignalR[int], Callable[[int], None]],
    build: BuildSession,
) -> None:
    """Count a subscribed slot as connected in the wiring report."""
    signal, _ = counter
    session = build(App)
    assert "watcher.on_reading" in session.unconnected.slots

    class Wired(App):
        def wire(self) -> Iterator[Link]:
            yield signal, self.watcher.on_reading

    wired = build(Wired)
    assert "watcher.on_reading" not in wired.unconnected.slots
