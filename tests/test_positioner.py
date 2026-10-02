"""Tests for the positioner built-ins in a session."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

import pytest
from qtpy import QtCore, QtWidgets

from redsun import AsDevice, AsPresenter, AsView, Declare, Link
from redsun.presenter import PositionerPresenter
from redsun.qt import QtSession
from redsun.view.qt.builtins import PositionerView
from tests.sdk.mocks import Stage

if TYPE_CHECKING:
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
        yield self.positioner_view.sig_stop, self.positioner.stop
        yield self.positioner_view.sig_configure, self.positioner.configure
        yield (
            self.positioner.sig_configuration,
            self.positioner_view.update_configuration,
        )


def wait_for(condition: Any, timeout: float = 5.0) -> None:
    """Process Qt events until *condition* holds, or fail after *timeout*."""
    end = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < end, "condition not met in time"
        QtCore.QCoreApplication.processEvents()
        time.sleep(0.01)


def test_a_step_from_the_view_moves_the_stage_and_comes_back_as_a_readback(
    qapp: QtWidgets.QApplication, config_home: Any, build: BuildSession
) -> None:
    """Step an axis from the view and show the stage's new readback."""
    session = build(Lab)
    view = session.positioner_view
    label = view.findChild(QtWidgets.QLabel, "readback:x")
    plus = view.findChild(QtWidgets.QPushButton, "plus:x")
    assert label is not None
    assert plus is not None

    plus.pressed.emit()

    wait_for(lambda: label.text() == "1.000")


def test_a_subclass_of_the_presenter_is_built_with_its_own_fields(
    qapp: QtWidgets.QApplication, config_home: Any, build: BuildSession
) -> None:
    """Build a dataclass subclass whose inherited fields name types its module lacks."""
    session = build(TaggedLab)

    assert session.positioner.tag == "left"
    assert set(session.positioner.axes) == {"stage"}


def test_the_built_ins_are_declared_from_a_session_file(
    qapp: QtWidgets.QApplication, config_home: Any, build: BuildSession
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
