from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from inspect import Parameter
from pathlib import Path
from typing import Any, Literal

import pytest
from bluesky.utils import MsgGenerator
from qtpy import QtWidgets as QtW

from redsun.engine.actions import Action, continous
from redsun.presenter.plan_spec import (
    ParamDescription,
    ParamKind,
    PlanSpec,
    _is_renderable,
    create_plan_spec,
)
from redsun.view.qt._widget_factory import create_param_widget
from redsun.view.qt.utils import ActionButton, create_plan_widget

pytestmark = pytest.mark.qt


@pytest.fixture(autouse=True)
def _application(qapp: QtW.QApplication) -> None:
    """Hold the session's application for every test here.

    The widgets are built without asking for one, so run alone the module
    made and lost its own, and the interpreter died between tests.
    """


def _simple_spec() -> PlanSpec:
    """Build a minimal plan spec with one int parameter."""

    def plan(frames: int = 1) -> MsgGenerator[None]:
        yield from ()

    return create_plan_spec(plan, {})


def _bool_spec() -> PlanSpec:
    """Build a plan spec with a bool parameter."""

    def plan(write_forever: bool = False) -> MsgGenerator[None]:
        yield from ()

    return create_plan_spec(plan, {})


def _literal_spec() -> PlanSpec:
    """Build a plan spec with a Literal parameter."""

    def plan(egu: Literal["um", "mm"] = "um") -> MsgGenerator[None]:
        yield from ()

    return create_plan_spec(plan, {})


def _int_literal_spec() -> PlanSpec:
    """Build a plan spec with a Literal of integers."""

    def plan(mode: Literal[1, 2, 3] = 2) -> MsgGenerator[None]:
        yield from ()

    return create_plan_spec(plan, {})


def _togglable_spec() -> PlanSpec:
    """Build a togglable plan spec (no pause)."""

    @continous(togglable=True, pausable=False)
    def plan() -> MsgGenerator[None]:
        yield from ()

    return create_plan_spec(plan, {})


def _pausable_spec() -> PlanSpec:
    """Build a togglable and pausable plan spec."""

    @continous(togglable=True, pausable=True)
    def plan() -> MsgGenerator[None]:
        yield from ()

    return create_plan_spec(plan, {})


def _action_spec() -> PlanSpec:
    """Build a plan spec with an action parameter."""

    @dataclass
    class Snap(Action):
        name: str = "snap"

    def plan(frames: int = 1, /, snap: Action = Snap()) -> MsgGenerator[None]:
        yield from ()

    return create_plan_spec(plan, {})


def _togglable_action_spec() -> PlanSpec:
    """Build a plan spec with a togglable action."""

    @dataclass
    class Stream(Action):
        name: str = "stream"
        togglable: bool = True
        toggle_states: tuple[str, str] = ("Start", "Stop")

    def plan(frames: int = 1, /, stream: Action = Stream()) -> MsgGenerator[None]:
        yield from ()

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
        assert btn.text() == "Stream (Start)"
        btn.setChecked(True)
        assert btn.text() == "Stream (Stop)"
        btn.setChecked(False)
        assert btn.text() == "Stream (Start)"


class TestCreatePlanWidget:
    """Tests for create_plan_widget output structure."""

    def test_simple_plan_has_no_pause_button(self) -> None:
        pw = create_plan_widget(_simple_spec())
        assert pw.pause_button is None

    def test_simple_plan_has_no_actions_group(self) -> None:
        pw = create_plan_widget(_simple_spec())
        assert pw.actions_group is None
        assert pw.action_buttons == {}

    def test_simple_plan_run_button_not_checkable(self) -> None:
        pw = create_plan_widget(_simple_spec())
        assert not pw.run_button.isCheckable()

    def test_togglable_plan_run_button_is_checkable(self) -> None:
        pw = create_plan_widget(_togglable_spec())
        assert pw.run_button.isCheckable()

    def test_togglable_plan_has_no_pause_button(self) -> None:
        pw = create_plan_widget(_togglable_spec())
        assert pw.pause_button is None

    def test_pausable_plan_has_pause_button(self) -> None:
        pw = create_plan_widget(_pausable_spec())
        assert pw.pause_button is not None

    def test_pausable_plan_pause_button_initially_disabled(self) -> None:
        pw = create_plan_widget(_pausable_spec())
        assert pw.pause_button is not None
        assert not pw.pause_button.isEnabled()

    def test_action_plan_has_actions_group(self) -> None:
        pw = create_plan_widget(_action_spec())
        assert pw.actions_group is not None

    def test_action_plan_actions_group_initially_disabled(self) -> None:
        pw = create_plan_widget(_action_spec())
        assert pw.actions_group is not None
        assert not pw.actions_group.isEnabled()

    def test_action_plan_has_action_button(self) -> None:
        pw = create_plan_widget(_action_spec())
        assert "snap" in pw.action_buttons

    def test_has_actions_true_when_actions_present(self) -> None:
        assert create_plan_widget(_action_spec()).has_actions()

    def test_has_actions_false_when_no_actions(self) -> None:
        assert not create_plan_widget(_simple_spec()).has_actions()

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
        assert create_plan_widget(_simple_spec()).parameters == {"frames": 1}

    def test_literal_param_in_parameters(self) -> None:
        assert create_plan_widget(_literal_spec()).parameters == {"egu": "um"}

    def test_a_literal_of_integers_yields_an_integer(self) -> None:
        assert create_plan_widget(_int_literal_spec()).parameters == {"mode": 2}

    def test_a_bool_parameter_shows_its_name_once(self) -> None:
        """The form row carries the name; the checkbox itself carries none.

        magicgui gives a CheckBox its name as text too, which rendered every
        bool parameter as "write forever [ ] write forever".
        """
        pw = create_plan_widget(_bool_spec())
        checkbox = pw.group_box.findChild(QtW.QCheckBox)

        assert checkbox is not None
        assert checkbox.text() == ""
        labels = [
            label.text()
            for label in pw.group_box.findChildren(QtW.QLabel)
            if label.text() == "write forever"
        ]
        assert labels == ["write forever"]
        assert pw.parameters == {"write_forever": False}

    def test_get_action_button_returns_button(self) -> None:
        pw = create_plan_widget(_action_spec())
        btn = pw.get_action_button("snap")
        assert btn is not None
        assert isinstance(btn, ActionButton)

    def test_get_action_button_returns_none_for_unknown(self) -> None:
        pw = create_plan_widget(_action_spec())
        assert pw.get_action_button("nonexistent") is None


class TestPlanWidgetControlAPI:
    """Tests for PlanWidget.toggle / pause / setEnabled / enable_actions."""

    def test_toggle_swaps_the_run_button_text(self) -> None:
        pw = create_plan_widget(_togglable_spec())
        pw.toggle(True)
        assert pw.run_button.text() == "Stop"
        pw.toggle(False)
        assert pw.run_button.text() == "Run"

    def test_toggle_enables_the_pause_button_while_running(self) -> None:
        pw = create_plan_widget(_pausable_spec())
        assert pw.pause_button is not None
        pw.toggle(True)
        assert pw.pause_button.isEnabled()
        pw.toggle(False)
        assert not pw.pause_button.isEnabled()

    def test_toggle_freezes_the_parameters_while_running(self) -> None:
        pw = create_plan_widget(_simple_spec())
        pw.toggle(True)
        assert not pw.params_widget.isEnabled()
        pw.toggle(False)
        assert pw.params_widget.isEnabled()

    def test_toggle_enables_actions_group(self) -> None:
        pw = create_plan_widget(_action_spec())
        pw.toggle(True)
        assert pw.actions_group is not None
        assert pw.actions_group.isEnabled()

    def test_pause_swaps_the_pause_button_text(self) -> None:
        pw = create_plan_widget(_pausable_spec())
        assert pw.pause_button is not None
        pw.toggle(True)
        pw.pause(True)
        assert pw.pause_button.text() == "Resume"
        pw.pause(False)
        assert pw.pause_button.text() == "Pause"

    def test_pause_true_disables_run_button(self) -> None:
        pw = create_plan_widget(_pausable_spec())
        pw.toggle(True)
        pw.pause(True)
        assert not pw.run_button.isEnabled()

    def test_set_enabled_reaches_the_group_box(self) -> None:
        pw = create_plan_widget(_simple_spec())
        pw.setEnabled(False)
        assert not pw.group_box.isEnabled()
        pw.setEnabled(True)
        assert pw.group_box.isEnabled()

    def test_enable_actions_reaches_the_actions_group(self) -> None:
        pw = create_plan_widget(_action_spec())
        assert pw.actions_group is not None
        pw.enable_actions(True)
        assert pw.actions_group.isEnabled()
        pw.enable_actions(False)
        assert not pw.actions_group.isEnabled()

    def test_enable_actions_noop_when_no_actions(self) -> None:
        """enable_actions should not raise when there is no actions_group."""
        pw = create_plan_widget(_simple_spec())
        pw.enable_actions(True)
        pw.enable_actions(False)


#: Annotations a required plan parameter might carry, spanning both sides of
#: the gate. Each is checked twice: whether `create_plan_spec` accepts it, and
#: whether the Qt view can build a control for it.
_ANNOTATIONS = [
    pytest.param(int, id="int"),
    pytest.param(float, id="float"),
    pytest.param(str, id="str"),
    pytest.param(bool, id="bool"),
    pytest.param(Path, id="path"),
    pytest.param(Sequence[int], id="sequence-int"),
    pytest.param(list[str], id="list-str"),
    pytest.param(Decimal, id="decimal"),
    pytest.param(Any, id="any"),
]


@pytest.mark.parametrize("annotation", _ANNOTATIONS)
def test_the_gate_agrees_with_the_widget_factory(annotation: Any) -> None:
    """What the presenter admits is what the Qt view can render, and vice versa.

    The two live in different layers and neither imports the other, so a type
    added to one and not the other goes unnoticed: a plan is either skipped
    though it was renderable, or admitted and then crashes the form.
    """
    # required, as the gate only refuses a parameter with no default
    param = ParamDescription(
        name="x",
        kind=ParamKind.POSITIONAL_OR_KEYWORD,
        annotation=annotation,
        default=Parameter.empty,
    )
    try:
        create_param_widget(param)
    except (RuntimeError, TypeError, ValueError):
        # what magicgui and the factory raise for an annotation neither can map
        renderable = False
    else:
        renderable = True

    assert _is_renderable(annotation) is renderable
