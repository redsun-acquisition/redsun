"""Tests for the acquisition view."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, TypeVar

import bluesky.plan_stubs as bps
import pytest
from bluesky.protocols import Readable
from bluesky.utils import MsgGenerator
from qtpy import QtCore, QtWidgets

from redsun import Settings
from redsun.presenter.plan_spec import create_plan_spec
from redsun.view.qt.builtins import AcquisitionView
from tests.sdk.mocks import MockDetector

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from redsun import CallbackType
    from redsun.presenter.plan_spec import PlanSpec

pytestmark = pytest.mark.qt

T = TypeVar("T", bound=QtCore.QObject)


def rest() -> MsgGenerator[None]:
    """End at once."""
    yield from bps.null()


def count(detectors: Sequence[Readable[Any]]) -> MsgGenerator[None]:
    """Read some detectors."""
    yield from bps.null()


class Acquisition:
    """Describes two plans, as an acquisition presenter would."""

    def __init__(self, names: Sequence[str] = ("rest", "count")) -> None:
        functions: dict[str, Callable[..., MsgGenerator[None]]] = {
            "rest": rest,
            "count": count,
        }
        self.plans: Mapping[str, PlanSpec] = {
            name: create_plan_spec(functions[name], {"det1": MockDetector("det1")})
            for name in names
        }
        self.callbacks: Mapping[str, CallbackType] = {}
        self.base_dir: Path | None = None
        self.plan_callbacks: Mapping[str, Sequence[CallbackType]] = {
            name: () for name in names
        }


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(tmp_path / "session.json")


@pytest.fixture
def parent(qapp: QtWidgets.QApplication) -> QtWidgets.QWidget:
    return QtWidgets.QWidget()


def make_view(
    settings: Settings, parent: QtWidgets.QWidget, acquisition: Any = None
) -> AcquisitionView:
    """Build an acquisition view in *parent*."""
    view = AcquisitionView("acquisition_view", parent)
    view.setup(acquisition or Acquisition(), settings)
    return view


def child(parent: QtCore.QObject, kind: type[T], name: str) -> T:
    """Return the child of *parent* of type *kind* named *name*."""
    found = parent.findChild(kind, name)
    assert found is not None
    return found


def choose(view: AcquisitionView, plan: str) -> None:
    """Select *plan* in the view's chooser."""
    child(view, QtWidgets.QComboBox, "plans").setCurrentText(plan)


def run_button(view: AcquisitionView, plan: str) -> QtWidgets.QPushButton:
    """Return the Run button of *plan*."""
    return view.plan_widgets[plan].run_button


def test_running_shows_only_once_the_presenter_has_started(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Ask to launch on Run, and lock the chooser only when the plan starts."""
    view = make_view(settings, parent)
    asked: list[tuple[Any, ...]] = []
    view.sig_launch.connect(lambda *args: asked.append(args))
    chooser = child(view, QtWidgets.QComboBox, "plans")
    choose(view, "rest")

    run_button(view, "rest").click()
    before = chooser.isEnabled()
    view.set_started("rest")

    assert asked == [("rest", {}, ())]
    assert (before, chooser.isEnabled()) == (True, False)


def test_a_failure_stays_shown_until_the_next_run(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Show why a plan failed, free the chooser, and clear the message on its next run."""
    view = make_view(settings, parent)
    failure = child(view, QtWidgets.QLabel, "failure:rest")

    view.set_started("rest")
    view.set_failed("rest", "bad target")
    shown = (failure.isHidden(), failure.text())
    view.set_started("rest")

    assert shown == (False, "failed: bad target")
    assert failure.isHidden()


def test_run_waits_for_a_device_to_be_chosen(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Enable Run only while a plan needing devices has one chosen."""
    view = make_view(settings, parent)
    button = run_button(view, "count")
    [detector] = [
        box for box in view.findChildren(QtWidgets.QCheckBox) if box.text() == "det1"
    ]

    enabled = [button.isEnabled()]
    detector.click()
    enabled.append(button.isEnabled())
    detector.click()
    enabled.append(button.isEnabled())

    assert enabled == [False, True, False]
    assert run_button(view, "rest").isEnabled()


def test_updates_for_an_unknown_plan_or_action_are_ignored(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Ignore progress and actions with no plan running, and an unknown plan's end."""
    view = make_view(settings, parent)

    view.update_progress(())
    view.update_action("go", "offered")
    view.set_done("ghost")


def test_a_session_without_plans_says_so(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Say no plans are offered when there are none."""
    view = make_view(settings, parent, Acquisition(names=()))

    assert child(view, QtWidgets.QLabel, "no-plans").text() == "No plans are offered."


def test_the_last_plan_chosen_is_offered_again(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Select again, in a later session, the plan chosen last."""
    first = make_view(settings, parent)
    offered = child(first, QtWidgets.QComboBox, "plans").currentText()
    choose(first, "rest")

    later = make_view(settings, parent)

    assert offered == "count"
    assert child(later, QtWidgets.QComboBox, "plans").currentText() == "rest"


def test_the_base_directory_is_shown_and_asked_for(
    parent: QtWidgets.QWidget,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Show the base directory reported, and ask for the one chosen in the dialog."""
    view = make_view(settings, parent)
    asked: list[object] = []
    view.sig_base_dir.connect(asked.append)
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(tmp_path),
    )

    view.update_base_dir(tmp_path / "data")
    child(view, QtWidgets.QPushButton, "choose-root").click()

    assert child(view, QtWidgets.QLineEdit, "base-dir").text() == str(tmp_path / "data")
    assert asked == [tmp_path]


def test_the_run_button_of_a_running_plan_stops_it(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Ask to stop, not to launch again, when Run is clicked on a running plan."""
    view = make_view(settings, parent)
    asked: list[str] = []
    view.sig_launch.connect(lambda *args: asked.append("launch"))
    view.sig_stop.connect(lambda: asked.append("stop"))
    choose(view, "rest")

    view.set_started("rest")
    run_button(view, "rest").click()

    assert asked == ["stop"]


def test_the_base_directory_is_shown_from_the_start(
    parent: QtWidgets.QWidget, settings: Settings, tmp_path: Path
) -> None:
    """Show the directory runs write under as soon as the view is set up."""
    acquisition = Acquisition()
    acquisition.base_dir = tmp_path

    view = make_view(settings, parent, acquisition)

    assert child(view, QtWidgets.QLineEdit, "base-dir").text() == str(tmp_path)
