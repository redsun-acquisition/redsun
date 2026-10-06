"""Tests for the links a pairing of two components makes."""

from __future__ import annotations

import pytest
from ophyd_async.core import soft_signal_rw
from psygnal import Signal

from redsun import links_between, slot


class Controller:
    """A presenter announcing moves and homing, and taking move requests."""

    sig_moved = Signal(str, float)
    sig_homed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[tuple[str, float]] = []

    @slot(signal="sig_requested")
    def move(self, axis: str, amount: float) -> None:
        self.requests.append((axis, amount))


class Panel:
    """A view showing positions, asking for moves, with one slot nothing names."""

    sig_requested = Signal(str, float)

    @slot(signal=("sig_moved", "sig_homed"))
    def refresh(self, axis: str, *rest: object) -> None: ...

    @slot(signal="sig_moved")
    def show_position(self, axis: str, position: float) -> None: ...

    @slot
    def clear(self) -> None: ...


class Mute:
    """A component with no ports a pairing could match."""


class Sensor:
    """A component holding a device signal under a name a slot asks for."""

    def __init__(self) -> None:
        super().__init__()
        self.sig_reading = soft_signal_rw(float, 0.0)


class Display:
    """A view with a slot naming the sensor's device signal."""

    @slot(signal="sig_reading")
    def show(self, value: object) -> None: ...


def test_a_pairing_links_each_named_signal_to_each_slot_both_ways() -> None:
    """Link every signal to every slot naming it, the first component's signals first."""
    controller = Controller()
    panel = Panel()

    links = links_between(controller, panel)

    assert links == [
        (controller.sig_homed, panel.refresh),
        (controller.sig_moved, panel.refresh),
        (controller.sig_moved, panel.show_position),
        (panel.sig_requested, controller.move),
    ]


@pytest.mark.parametrize(
    ("first", "second"),
    [(Controller, Mute), (Sensor, Display)],
    ids=["no-name-matches", "device-signal"],
)
def test_a_pairing_with_nothing_to_match_gives_no_links(
    first: type, second: type
) -> None:
    """Return no link when no slot names a signal, a device signal included."""
    assert links_between(first(), second()) == []


def test_a_component_cannot_be_paired_with_itself() -> None:
    """Refuse to pair a component with itself."""
    controller = Controller()

    with pytest.raises(ValueError, match="with itself"):
        links_between(controller, controller)
