"""Tests for the positioner built-ins in a session."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

import pytest
from qtpy import QtWidgets

from redsun import AsDevice, AsPresenter, AsView, Declare, Link
from redsun.presenter import AcquisitionPresenter, PositionerPresenter
from redsun.qt import QtSession
from redsun.view.qt.builtins import PositionerView
from tests.sdk.mocks import Stage

if TYPE_CHECKING:
    from collections.abc import Callable

    from redsun.testing import BuildSession

pytestmark = pytest.mark.qt


@dataclass(eq=False, kw_only=True)
class TaggedPositioner(PositionerPresenter):
    """A positioner with a field of its own, declared in a module of its own."""

    tag: str = ""


class TaggedLab(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "positioner-tagged"}

    stage: AsDevice[Stage]
    positioner: Annotated[AsPresenter[TaggedPositioner], Declare(tag="left")]


class Lab(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "positioner-lab"}

    stage: AsDevice[Stage]
    positioner: AsPresenter[PositionerPresenter]
    positioner_view: AsView[PositionerView]

    def wire(self) -> Iterator[Link]:
        yield self.positioner_view.sig_move, self.positioner.move
        yield self.positioner_view.sig_move_to, self.positioner.move_to
        yield self.positioner.sig_readback, self.positioner_view.update_readback
        yield self.positioner.sig_moving, self.positioner_view.set_moving
        yield self.positioner.sig_failed, self.positioner_view.set_failed
        yield self.positioner.sig_limits, self.positioner_view.update_limits
        yield self.positioner_view.sig_stop_device, self.positioner.stop
        yield self.positioner_view.sig_configure, self.positioner.configure
        yield (
            self.positioner.sig_configuration,
            self.positioner_view.update_configuration,
        )


class PairedLab(QtSession):
    config: ClassVar[dict[str, Any]] = {
        "session": "positioner-paired",
        "pairs": [["positioner_view", "positioner"]],
    }

    stage: AsDevice[Stage]
    positioner: AsPresenter[PositionerPresenter]
    positioner_view: AsView[PositionerView]


class LockedLab(QtSession):
    config: ClassVar[dict[str, Any]] = {
        "session": "positioner-locked",
        "pairs": [["acquisition", "positioner_view"], ["acquisition", "positioner"]],
    }

    stage: AsDevice[Stage]
    acquisition: AsPresenter[AcquisitionPresenter]
    positioner: AsPresenter[PositionerPresenter]
    positioner_view: AsView[PositionerView]


@pytest.mark.parametrize("lab", [Lab, PairedLab])
def test_a_step_from_the_view_moves_the_stage_and_comes_back_as_a_readback(
    qapp: QtWidgets.QApplication,
    build: BuildSession,
    wait_until: Callable[..., bool],
    lab: type[QtSession],
) -> None:
    """Step an axis from the view, wired by hand or paired, and show the new readback."""
    session = build(lab)
    view = session.views["positioner_view"]
    assert isinstance(view, PositionerView)
    label = view.findChild(QtWidgets.QLabel, "readback:x")
    plus = view.findChild(QtWidgets.QAbstractButton, "plus:x")
    assert label is not None
    assert plus is not None

    plus.pressed.emit()

    assert wait_until(lambda: label.text() == "1.000")


@pytest.mark.parametrize("consumer", ["positioner_view", "positioner"])
def test_pairing_the_acquisition_presenter_passes_on_locks_only(
    qapp: QtWidgets.QApplication, build: BuildSession, consumer: str
) -> None:
    """Link only the locks to the view or the presenter, so stopping one device never reaches the plan."""
    session = build(LockedLab)

    links = {
        (c.publisher, c.publisher_port, c.consumer, c.consumer_port)
        for c in session.connections
        if {c.publisher, c.consumer} == {"acquisition", consumer}
    }

    assert links == {("acquisition", "sig_locks_changed", consumer, "set_locked")}


def test_pairing_the_positioner_makes_every_link_of_the_stack(
    qapp: QtWidgets.QApplication, build: BuildSession
) -> None:
    """Link every signal and slot the positioner and its view offer each other."""
    session = build(PairedLab)

    assert {
        (c.publisher, c.publisher_port, c.consumer, c.consumer_port)
        for c in session.connections
    } == {
        ("positioner_view", "sig_move", "positioner", "move"),
        ("positioner_view", "sig_move_to", "positioner", "move_to"),
        ("positioner_view", "sig_stop_device", "positioner", "stop"),
        ("positioner_view", "sig_configure", "positioner", "configure"),
        ("positioner", "sig_readback", "positioner_view", "update_readback"),
        ("positioner", "sig_limits", "positioner_view", "update_limits"),
        ("positioner", "sig_moving", "positioner_view", "set_moving"),
        ("positioner", "sig_failed", "positioner_view", "set_failed"),
        ("positioner", "sig_configuration", "positioner_view", "update_configuration"),
    }


def test_a_subclass_of_the_presenter_is_built_with_its_own_fields(
    qapp: QtWidgets.QApplication, build: BuildSession
) -> None:
    """Build a dataclass subclass whose inherited fields name types its module lacks."""
    session = build(TaggedLab)

    assert session.positioner.tag == "left"
    assert set(session.positioner.axes) == {"stage"}


def test_the_built_ins_are_declared_from_a_session_file(
    qapp: QtWidgets.QApplication, build: BuildSession
) -> None:
    """Build the positioner pair by plugin id from a session file."""
    session = build(
        QtSession.from_config(
            {
                "session": "positioner-file",
                "presenters": {
                    "positioner": {"plugin_name": "redsun", "plugin_id": "positioner"}
                },
                "views": {
                    "positioner_view": {
                        "plugin_name": "redsun",
                        "plugin_id": "positioner",
                    }
                },
                "wiring": {
                    "positioner_view.sig_move": "positioner.move",
                    "positioner.sig_readback": "positioner_view.update_readback",
                },
            }
        )
    )

    assert isinstance(session.presenters["positioner"], PositionerPresenter)
    assert isinstance(session.views["positioner_view"], PositionerView)
