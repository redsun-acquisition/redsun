"""Tests for the acquisition built-ins in a session."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from qtpy import QtWidgets

from docs.examples.acquisition import MyApp
from redsun import AsPresenter, Link, Session
from redsun.aio import run_coro
from redsun.engine import Deferrals, RunEngine
from redsun.presenter import AcquisitionPresenter
from redsun.qt import QtSession
from redsun.view.qt.builtins import AcquisitionView

if TYPE_CHECKING:
    from collections.abc import Callable

    from redsun.testing import BuildSession


class Follower:
    """A presenter that asks for the engine and its deferrals."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.engine: RunEngine | None = None
        self.deferrals: Deferrals | None = None

    def setup(self, engine: RunEngine, deferrals: Deferrals) -> None:
        """Keep what the session shares."""
        self.engine = engine
        self.deferrals = deferrals


class Lab(Session):
    config: ClassVar[dict[str, Any]] = {"session": "acquisition-lab"}

    acquisition: AsPresenter[AcquisitionPresenter]
    follower: AsPresenter[Follower]

    def wire(self) -> Iterator[Link]:
        yield from ()


class TwoRunners(Session):
    config: ClassVar[dict[str, Any]] = {"session": "acquisition-twice"}

    first: AsPresenter[AcquisitionPresenter]
    second: AsPresenter[AcquisitionPresenter]


def test_the_engine_and_deferrals_reach_a_component_that_asks(
    build: BuildSession,
) -> None:
    """Give a component asking for a `RunEngine` and `Deferrals` the presenter's own."""
    session = build(Lab)

    assert session.follower.engine is session.acquisition.engine()
    assert session.follower.deferrals is session.acquisition.deferrals()


def test_a_session_with_two_acquisition_presenters_is_refused() -> None:
    """Refuse a session in which two acquisition presenters share an engine."""
    with pytest.raises(TypeError, match="share"):
        TwoRunners().build()


@pytest.mark.qt
def test_a_plan_launched_from_the_view_moves_the_motor_and_ends(
    qapp: QtWidgets.QApplication,
    build: BuildSession,
    wait_until: Callable[..., bool],
) -> None:
    """Run a plan from the view and see it move the motor and end."""
    session = build(MyApp, {"mock": True, "strict": True})
    chooser = session.acquisition_view.findChild(QtWidgets.QComboBox, "plans")
    assert chooser is not None

    ended: list[str] = []
    session.acquisition.sig_plan_done.connect(ended.append)

    session.acquisition_view.sig_launch.emit(
        "walk", {"motor": "motor", "steps": 3, "size": 1.0}, ()
    )
    # the view hears of the end on the main thread, after the presenter reports it
    assert wait_until(lambda: bool(ended) and chooser.isEnabled())

    assert ended == ["walk"]
    assert run_coro(session.motor.position.get_value()) == 3.0


@pytest.mark.qt
def test_the_stack_is_declared_from_a_session_file(
    qapp: QtWidgets.QApplication, build: BuildSession
) -> None:
    """Build the acquisition presenter and view a session file names by plugin id."""
    session = build(
        QtSession,
        {
            "session": "acquisition-file",
            "presenters": {
                "acquisition": {"plugin_name": "redsun", "plugin_id": "acquisition"}
            },
            "views": {
                "acquisition_view": {
                    "plugin_name": "redsun",
                    "plugin_id": "acquisition",
                }
            },
        },
    )

    assert isinstance(session.presenters["acquisition"], AcquisitionPresenter)
    assert isinstance(session.views["acquisition_view"], AcquisitionView)
