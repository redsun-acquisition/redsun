"""Tests for the report of ports no connection reaches."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from psygnal import Signal, SignalGroup

from redsun.experimental import AsPresenter, Session, WiringError, slot
from redsun.experimental.ports._wiring import Unconnected, ports

if TYPE_CHECKING:
    from .conftest import BuildSession


class Moves(SignalGroup):
    """A group whose members are ports in their own right."""

    started = Signal(str)
    finished = Signal(str)


class Stage:
    """Presenter exposing one signal and one slot, neither wired by default."""

    sig_moved = Signal(float)

    def __init__(self, name: str, /) -> None:
        self.name = name

    @slot
    def halt(self) -> None:
        self.halted = True


class Grouped:
    """Presenter whose ports arrive through a signal group."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.moves = Moves()


class Clashing:
    """Presenter naming one port twice, as an attribute and a group member."""

    started = Signal(str)

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.moves = Moves()


class App(Session):
    config: ClassVar[dict[str, Any]] = {"name": "reporting"}

    stage: AsPresenter[Stage]
    other: AsPresenter[Stage]


def test_a_session_wired_to_nothing_reports_every_port(
    build: BuildSession,
) -> None:
    report = build(App).unconnected

    assert set(report.signals) == {"stage.sig_moved", "other.sig_moved"}
    assert set(report.slots) == {"stage.halt", "other.halt"}


def test_a_connected_pair_leaves_the_report(build: BuildSession) -> None:
    session = build(App)

    session.connect(session.stage.sig_moved, session.other.halt)

    assert "stage.sig_moved" not in session.unconnected.signals
    assert "other.halt" not in session.unconnected.slots
    assert "other.sig_moved" in session.unconnected.signals


def test_a_fully_wired_session_reports_nothing(
    build: BuildSession,
) -> None:
    session = build(App)
    session.connect(session.stage.sig_moved, session.other.halt)
    session.connect(session.other.sig_moved, session.stage.halt)

    report = session.unconnected

    assert not report
    assert str(report) == "every port is connected"


def test_the_report_says_which_end_is_missing() -> None:
    report = Unconnected(signals=["stage.sig_moved"], slots=["panel.refresh"])

    assert str(report).splitlines() == [
        "stage.sig_moved -> nothing",
        "nothing -> panel.refresh",
    ]


def test_a_group_member_is_a_port_of_the_component_that_holds_it() -> None:
    """A signal group is a way of writing ports, not a component of its own."""
    surface = ports(Grouped("grouped"))

    assert set(surface.signals) == {"started", "finished"}


def test_one_port_name_may_not_come_from_two_places() -> None:
    """A path in a wiring rule has to mean one signal, so the clash is refused."""
    with pytest.raises(WiringError, match="exposes two signals named 'started'"):
        ports(Clashing("clashing"))
