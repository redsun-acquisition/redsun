"""Tests for the acquisition built-ins in a session."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from qtpy import QtWidgets

from docs.examples.acquisition import MyApp, MyMotor, MyPlans
from redsun import AsDevice, AsPresenter, AsView, Link, Session
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


class PairedApp(QtSession):
    config: ClassVar[dict[str, Any]] = {
        "session": "acquisition-paired",
        "pairs": [["acquisition_view", "acquisition"]],
    }

    motor: AsDevice[MyMotor]
    plans: AsPresenter[MyPlans]
    acquisition: AsPresenter[AcquisitionPresenter]
    acquisition_view: AsView[AcquisitionView]


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
def test_pairing_the_acquisition_makes_every_link_of_the_stack(
    qapp: QtWidgets.QApplication, build: BuildSession
) -> None:
    """Link every signal and slot the acquisition presenter and its view offer each other."""
    session = build(PairedApp, {"mock": True, "strict": True})

    assert {
        (c.publisher, c.publisher_port, c.consumer, c.consumer_port)
        for c in session.connections
    } == {
        ("acquisition_view", "sig_launch", "acquisition", "launch"),
        ("acquisition_view", "sig_pause", "acquisition", "pause"),
        ("acquisition_view", "sig_resume", "acquisition", "resume"),
        ("acquisition_view", "sig_stop", "acquisition", "stop"),
        ("acquisition_view", "sig_action", "acquisition", "request_action"),
        ("acquisition_view", "sig_base_dir", "acquisition", "set_base_dir"),
        ("acquisition", "sig_plan_started", "acquisition_view", "set_started"),
        ("acquisition", "sig_plan_done", "acquisition_view", "set_done"),
        ("acquisition", "sig_plan_failed", "acquisition_view", "set_failed"),
        ("acquisition", "sig_progress", "acquisition_view", "update_progress"),
        ("acquisition", "sig_action_changed", "acquisition_view", "update_action"),
        ("acquisition", "sig_base_dir_changed", "acquisition_view", "update_base_dir"),
    }


@pytest.mark.qt
@pytest.mark.parametrize(
    "app", [MyApp, PairedApp], ids=["wired-by-links_between", "paired-in-config"]
)
def test_a_plan_launched_from_the_view_moves_the_motor_and_ends(
    qapp: QtWidgets.QApplication,
    build: BuildSession,
    wait_until: Callable[..., bool],
    app: type[QtSession],
) -> None:
    """Run a plan from the view, paired from `wire` or from the config, and see it start and end."""
    session = build(app, {"mock": True, "strict": True})
    acquisition = session.presenters["acquisition"]
    view = session.views["acquisition_view"]
    assert isinstance(acquisition, AcquisitionPresenter)
    assert isinstance(view, AcquisitionView)
    chooser = view.findChild(QtWidgets.QComboBox, "plans")
    assert chooser is not None

    ended: list[str] = []
    acquisition.sig_plan_done.connect(ended.append)

    acquisition.sig_plan_started.emit("walk")
    assert wait_until(lambda: not chooser.isEnabled())

    view.sig_launch.emit("walk", {"motor": "motor", "steps": 3, "size": 1.0}, ())
    # the view hears of the end on the main thread, after the presenter reports it
    assert wait_until(lambda: bool(ended) and chooser.isEnabled())

    assert ended == ["walk"]
    motor = session.devices["motor"]
    assert isinstance(motor, MyMotor)
    assert run_coro(motor.position.get_value()) == 3.0


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


@pytest.mark.qt
def test_the_view_binds_its_run_and_stop_keys(
    qapp: QtWidgets.QApplication, build: BuildSession
) -> None:
    """Bind Ctrl+R and Ctrl+. to the view's run and stop in a strict session."""
    session = build(PairedApp, {"mock": True, "strict": True})

    keys = {b.command: b.keys for b in session.resolve_shortcuts()}

    assert keys["acquisition_view.run_plan"] == ("Ctrl+R",)
    assert keys["acquisition_view.stop_plan"] == ("Ctrl+.",)
