from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Literal

import pytest
from bluesky.utils import MsgGenerator

from redsun.engine.actions import Action, continous
from redsun.presenter.plan_spec import PlanSpec, create_plan_spec
from redsun.view.qt.utils import ActionButton, PlanWidget, create_plan_widget

pytestmark = pytest.mark.skipif(
    sys.platform == "linux" and not os.environ.get("DISPLAY"),
    reason="requires a display (Qt) on Linux",
)


def _simple_spec() -> PlanSpec:
    """Build a minimal plan spec with one int parameter."""

    def plan(frames: int = 1) -> MsgGenerator[None]:
        yield

    return create_plan_spec(plan, {})


def _literal_spec() -> PlanSpec:
    """Build a plan spec with a Literal parameter."""

    def plan(egu: Literal["um", "mm"] = "um") -> MsgGenerator[None]:
        yield

    return create_plan_spec(plan, {})


def _togglable_spec() -> PlanSpec:
    """Build a togglable plan spec (no pause)."""

    @continous(togglable=True, pausable=False)
    def plan() -> MsgGenerator[None]:
        yield

    return create_plan_spec(plan, {})


def _pausable_spec() -> PlanSpec:
    """Build a togglable and pausable plan spec."""

    @continous(togglable=True, pausable=True)
    def plan() -> MsgGenerator[None]:
        yield

    return create_plan_spec(plan, {})


def _action_spec() -> PlanSpec:
    """Build a plan spec with an action parameter."""

    @dataclass
    class Snap(Action):
        name: str = "snap"

    def plan(frames: int = 1, /, snap: Action = Snap()) -> MsgGenerator[None]:
        yield

    return create_plan_spec(plan, {})


def _togglable_action_spec() -> PlanSpec:
    """Build a plan spec with a togglable action."""

    @dataclass
    class Stream(Action):
        name: str = "stream"
        togglable: bool = True
        toggle_states: tuple[str, str] = ("Start", "Stop")

    def plan(frames: int = 1, /, stream: Action = Stream()) -> MsgGenerator[None]:
        yield

    return create_plan_spec(plan, {})


class TestActionButton:
    """Tests for ActionButton."""

    def test_initial_label_is_capitalised_name(self) -> None:
        @dataclass
        class Go(Action):
            name: str = "go"

        btn = ActionButton(Go())
        assert btn.text() == "Go"

    def test_tooltip_set_when_description_present(self) -> None:
        @dataclass
        class Go(Action):
            name: str = "go"
            description: str = "Start acquisition"

        btn = ActionButton(Go())
        assert btn.toolTip() == "Start acquisition"

    def test_not_checkable_for_non_togglable_action(self) -> None:
        @dataclass
        class Go(Action):
            name: str = "go"
            togglable: bool = False

        btn = ActionButton(Go())
        assert not btn.isCheckable()

    def test_checkable_for_togglable_action(self) -> None:
        @dataclass
        class Stream(Action):
            name: str = "stream"
            togglable: bool = True
            toggle_states: tuple[str, str] = ("Start", "Stop")

        btn = ActionButton(Stream())
        assert btn.isCheckable()

    def test_label_updates_on_toggle(self) -> None:
        @dataclass
        class Stream(Action):
            name: str = "stream"
            togglable: bool = True
            toggle_states: tuple[str, str] = ("Start", "Stop")

        btn = ActionButton(Stream())
        # unchecked → first state label
        assert "Start" in btn.text()
        btn.setChecked(True)
        assert "Stop" in btn.text()
        btn.setChecked(False)
        assert "Start" in btn.text()


# ---------------------------------------------------------------------------
# PlanWidget helpers — build a minimal PlanWidget without Qt machinery
# ---------------------------------------------------------------------------


def _make_minimal_plan_widget(spec: PlanSpec) -> PlanWidget:
    """Create a PlanWidget via create_plan_widget with no callbacks."""
    return create_plan_widget(spec)


# ---------------------------------------------------------------------------
# create_plan_widget: structure
# ---------------------------------------------------------------------------


class TestCreatePlanWidget:
    """Tests for create_plan_widget output structure."""

    def test_simple_plan_has_no_pause_button(self) -> None:
        pw = _make_minimal_plan_widget(_simple_spec())
        assert pw.pause_button is None

    def test_simple_plan_has_no_actions_group(self) -> None:
        pw = _make_minimal_plan_widget(_simple_spec())
        assert pw.actions_group is None
        assert pw.action_buttons == {}

    def test_simple_plan_run_button_not_checkable(self) -> None:
        pw = _make_minimal_plan_widget(_simple_spec())
        assert not pw.run_button.isCheckable()

    def test_togglable_plan_run_button_is_checkable(self) -> None:
        pw = _make_minimal_plan_widget(_togglable_spec())
        assert pw.run_button.isCheckable()

    def test_togglable_plan_has_no_pause_button(self) -> None:
        pw = _make_minimal_plan_widget(_togglable_spec())
        assert pw.pause_button is None

    def test_pausable_plan_has_pause_button(self) -> None:
        pw = _make_minimal_plan_widget(_pausable_spec())
        assert pw.pause_button is not None

    def test_pausable_plan_pause_button_initially_disabled(self) -> None:
        pw = _make_minimal_plan_widget(_pausable_spec())
        assert pw.pause_button is not None
        assert not pw.pause_button.isEnabled()

    def test_action_plan_has_actions_group(self) -> None:
        pw = _make_minimal_plan_widget(_action_spec())
        assert pw.actions_group is not None

    def test_action_plan_actions_group_initially_disabled(self) -> None:
        pw = _make_minimal_plan_widget(_action_spec())
        assert pw.actions_group is not None
        assert not pw.actions_group.isEnabled()

    def test_action_plan_has_action_button(self) -> None:
        pw = _make_minimal_plan_widget(_action_spec())
        assert "snap" in pw.action_buttons

    def test_has_actions_true_when_actions_present(self) -> None:
        assert _make_minimal_plan_widget(_action_spec()).has_actions()

    def test_has_actions_false_when_no_actions(self) -> None:
        assert not _make_minimal_plan_widget(_simple_spec()).has_actions()

    def test_group_box_is_qwidget(self) -> None:
        from qtpy import QtWidgets as QtW

        pw = _make_minimal_plan_widget(_simple_spec())
        assert isinstance(pw.group_box, QtW.QWidget)

    def test_spec_stored_on_widget(self) -> None:
        spec = _simple_spec()
        pw = create_plan_widget(spec)
        assert pw.spec is spec

    def test_run_callback_connected(self) -> None:
        """run_callback fires when run_button is clicked on a non-togglable plan."""
        fired: list[bool] = []
        pw = create_plan_widget(_simple_spec(), run_callback=lambda: fired.append(True))
        pw.run_button.click()
        assert fired == [True]

    def test_toggle_callback_connected(self) -> None:
        """toggle_callback fires when run_button is toggled on a togglable plan."""
        states: list[bool] = []
        pw = create_plan_widget(
            _togglable_spec(), toggle_callback=lambda checked: states.append(checked)
        )
        pw.run_button.setChecked(True)
        assert True in states

    def test_parameters_returns_current_values(self) -> None:
        pw = _make_minimal_plan_widget(_simple_spec())
        params = pw.parameters
        assert "frames" in params
        assert params["frames"] == 1  # default value

    def test_literal_param_in_parameters(self) -> None:
        pw = _make_minimal_plan_widget(_literal_spec())
        assert "egu" in pw.parameters

    def test_get_action_button_returns_button(self) -> None:
        pw = _make_minimal_plan_widget(_action_spec())
        btn = pw.get_action_button("snap")
        assert btn is not None
        assert isinstance(btn, ActionButton)

    def test_get_action_button_returns_none_for_unknown(self) -> None:
        pw = _make_minimal_plan_widget(_action_spec())
        assert pw.get_action_button("nonexistent") is None


# ---------------------------------------------------------------------------
# PlanWidget: runtime control API
# ---------------------------------------------------------------------------


class TestPlanWidgetControlAPI:
    """Tests for PlanWidget.toggle / pause / setEnabled / enable_actions."""

    def test_toggle_true_changes_run_button_text(self) -> None:
        pw = _make_minimal_plan_widget(_togglable_spec())
        pw.toggle(True)
        assert pw.run_button.text() == "Stop"

    def test_toggle_false_restores_run_button_text(self) -> None:
        pw = _make_minimal_plan_widget(_togglable_spec())
        pw.toggle(True)
        pw.toggle(False)
        assert pw.run_button.text() == "Run"

    def test_toggle_true_enables_pause_button(self) -> None:
        pw = _make_minimal_plan_widget(_pausable_spec())
        pw.toggle(True)
        assert pw.pause_button is not None
        assert pw.pause_button.isEnabled()

    def test_toggle_false_disables_pause_button(self) -> None:
        pw = _make_minimal_plan_widget(_pausable_spec())
        pw.toggle(True)
        pw.toggle(False)
        assert pw.pause_button is not None
        assert not pw.pause_button.isEnabled()

    def test_toggle_true_disables_params_widget(self) -> None:
        pw = _make_minimal_plan_widget(_simple_spec())
        pw.toggle(True)
        assert not pw.params_widget.isEnabled()

    def test_toggle_false_enables_params_widget(self) -> None:
        pw = _make_minimal_plan_widget(_simple_spec())
        pw.toggle(True)
        pw.toggle(False)
        assert pw.params_widget.isEnabled()

    def test_toggle_enables_actions_group(self) -> None:
        pw = _make_minimal_plan_widget(_action_spec())
        pw.toggle(True)
        assert pw.actions_group is not None
        assert pw.actions_group.isEnabled()

    def test_pause_true_changes_pause_button_text(self) -> None:
        pw = _make_minimal_plan_widget(_pausable_spec())
        pw.toggle(True)
        pw.pause(True)
        assert pw.pause_button is not None
        assert pw.pause_button.text() == "Resume"

    def test_pause_false_restores_pause_button_text(self) -> None:
        pw = _make_minimal_plan_widget(_pausable_spec())
        pw.toggle(True)
        pw.pause(True)
        pw.pause(False)
        assert pw.pause_button is not None
        assert pw.pause_button.text() == "Pause"

    def test_pause_true_disables_run_button(self) -> None:
        pw = _make_minimal_plan_widget(_pausable_spec())
        pw.toggle(True)
        pw.pause(True)
        assert not pw.run_button.isEnabled()

    def test_set_enabled_false_disables_group_box(self) -> None:
        pw = _make_minimal_plan_widget(_simple_spec())
        pw.setEnabled(False)
        assert not pw.group_box.isEnabled()

    def test_set_enabled_true_restores_group_box(self) -> None:
        pw = _make_minimal_plan_widget(_simple_spec())
        pw.setEnabled(False)
        pw.setEnabled(True)
        assert pw.group_box.isEnabled()

    def test_enable_actions_true_enables_actions_group(self) -> None:
        pw = _make_minimal_plan_widget(_action_spec())
        pw.enable_actions(True)
        assert pw.actions_group is not None
        assert pw.actions_group.isEnabled()

    def test_enable_actions_false_disables_actions_group(self) -> None:
        pw = _make_minimal_plan_widget(_action_spec())
        pw.enable_actions(True)
        pw.enable_actions(False)
        assert pw.actions_group is not None
        assert not pw.actions_group.isEnabled()

    def test_enable_actions_noop_when_no_actions(self) -> None:
        """enable_actions should not raise when there is no actions_group."""
        pw = _make_minimal_plan_widget(_simple_spec())
        pw.enable_actions(True)  # must not raise
        pw.enable_actions(False)
