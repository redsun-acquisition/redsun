"""Tests for the report of ports no connection reaches."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from psygnal import Signal, SignalGroup

from redsun import AsPresenter, Session, WiringError, slot
from redsun.ports import Unconnected, ports

if TYPE_CHECKING:
    from collections.abc import Iterator

    from redsun import Link
    from redsun.testing import BuildSession


class Moves(SignalGroup):
    """A group whose members are ports in their own right."""

    started = Signal(str)
    finished = Signal(str)


class Stage:
    """Presenter exposing one signal and one slot, neither wired by default."""

    sig_moved = Signal(float)

    def __init__(self, name: str) -> None:
        self.name = name

    @slot
    def halt(self) -> None:
        self.halted = True


class Grouped:
    """Presenter whose ports arrive through a signal group."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.moves = Moves()


class Clashing:
    """Presenter naming one port twice, as an attribute and a group member."""

    started = Signal(str)

    def __init__(self, name: str) -> None:
        self.name = name
        self.moves = Moves()


class Relay:
    """An object with ports of its own, for a presenter to hold."""

    sig_passed = Signal(float)

    @slot
    def take(self, position: float) -> None:
        self.taken = position


class Holding:
    """Presenter whose ports are those of an object it holds."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.relay = Relay()


class App(Session):
    config: ClassVar[dict[str, Any]] = {"session": "reporting"}

    stage: AsPresenter[Stage]
    other: AsPresenter[Stage]


def test_a_session_wired_to_nothing_reports_every_port(
    build: BuildSession,
) -> None:
    """Report every port of a session with no wiring as unconnected."""
    report = build(App).unconnected

    assert set(report.signals) == {"stage.sig_moved", "other.sig_moved"}
    assert set(report.slots) == {"stage.halt", "other.halt"}


def test_a_connected_pair_leaves_the_report(build: BuildSession) -> None:
    """Drop both ends of a connection from the unconnected report."""

    class HalfWired(App):
        def wire(self) -> Iterator[Link]:
            yield self.stage.sig_moved, self.other.halt

    session = build(HalfWired)

    assert "stage.sig_moved" not in session.unconnected.signals
    assert "other.halt" not in session.unconnected.slots
    assert "other.sig_moved" in session.unconnected.signals


def test_a_fully_wired_session_reports_nothing(
    build: BuildSession,
) -> None:
    """Report nothing unconnected once every port is wired."""

    class FullyWired(App):
        def wire(self) -> Iterator[Link]:
            yield self.stage.sig_moved, self.other.halt
            yield self.other.sig_moved, self.stage.halt

    session = build(FullyWired)
    report = session.unconnected

    assert not report
    assert str(report) == "every port is connected"


def test_a_port_of_an_object_a_presenter_holds_is_recorded_under_the_presenter(
    build: BuildSession,
) -> None:
    """Record a port of an object a presenter holds under the presenter's name."""

    class Held(Session):
        config: ClassVar[dict[str, Any]] = {"session": "reporting"}

        stage: AsPresenter[Stage]
        holder: AsPresenter[Holding]

        def wire(self) -> Iterator[Link]:
            yield self.stage.sig_moved, self.holder.relay.take
            yield self.holder.relay.sig_passed, self.stage.halt

    links = build(Held).connections

    assert [
        (link.publisher, link.publisher_port, link.consumer, link.consumer_port)
        for link in links
    ] == [
        ("stage", "sig_moved", "holder", "take"),
        ("holder", "sig_passed", "stage", "halt"),
    ]


def test_the_report_says_which_end_is_missing() -> None:
    """Show `nothing` at the missing end of each unconnected port."""
    report = Unconnected(signals=["stage.sig_moved"], slots=["panel.refresh"])

    assert str(report).splitlines() == [
        "stage.sig_moved -> nothing",
        "nothing -> panel.refresh",
    ]


def test_a_group_member_is_a_port_of_the_component_that_holds_it() -> None:
    """Count a signal group member as a port of the component holding the group."""
    surface = ports(Grouped("grouped"))

    assert set(surface.signals) == {"started", "finished"}


def test_one_port_name_may_not_come_from_two_places() -> None:
    """Refuse a component exposing two signals under one port name."""
    with pytest.raises(WiringError, match="exposes two signals named 'started'"):
        ports(Clashing("clashing"))
