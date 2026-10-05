from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from inspect import Parameter
from pathlib import Path
from typing import Any, Literal

import pytest
from bluesky.utils import MsgGenerator
from qtpy import QtCore
from qtpy import QtWidgets as QtW

from redsun.engine import ProgressState
from redsun.engine.actions import PlanAction, continuous
from redsun.presenter.plan_spec import (
    ParamDescription,
    ParamKind,
    PlanSpec,
    UnresolvableAnnotationError,
    create_plan_spec,
)
from redsun.view.qt._widget_factory import create_param_widget
from redsun.view.qt.utils import ActionButton, PlanWidget, create_plan_widget

pytestmark = pytest.mark.qt

STREAM = PlanAction(name="stream", toggle_states=("Start", "Stop"))


@pytest.fixture(autouse=True)
def _application(qapp: QtW.QApplication) -> None:
    """Hold the session's application for every test here.

    The widgets are built without asking for one, so run alone the module
    made and lost its own, and the interpreter died between tests.
    """


class Callback:
    """A document callback of the ordinary shape."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, name: str, doc: Any) -> None: ...


CALLBACKS = {name: Callback(name) for name in ("a", "b", "c", "own")}
"""Every callback the tests hand a plan widget, by name."""

CATALOGUE = {name: CALLBACKS[name] for name in ("a", "b", "c")}
"""The callbacks a user may attach; `own` is only ever carried by a plan."""


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


def _continuous_spec() -> PlanSpec:
    """Build a continuous plan spec (no pause)."""

    @continuous
    def plan() -> MsgGenerator[None]:
        yield from ()

    return create_plan_spec(plan, {})


def _pausable_spec() -> PlanSpec:
    """Build a continuous and pausable plan spec."""

    @continuous(pausable=True)
    def plan() -> MsgGenerator[None]:
        yield from ()

    return create_plan_spec(plan, {})


def _action_spec() -> PlanSpec:
    """Build a plan spec with an action parameter."""

    def plan(
        frames: int = 1, /, snap: PlanAction = PlanAction(name="snap")
    ) -> MsgGenerator[None]:
        yield from ()

    return create_plan_spec(plan, {})


def _scope(
    name: str,
    *,
    parent: str | None = None,
    current: float | None = None,
    target: float | None = None,
    fraction: float | None = None,
    unit: str = "frames",
    precision: int | None = None,
    time_remaining: float | None = None,
) -> ProgressState:
    """Build the state of one progress scope."""
    return ProgressState(
        name=name,
        parent=parent,
        current=current,
        initial=0.0 if target is not None else None,
        target=target,
        unit=unit,
        precision=precision,
        fraction=fraction,
        time_elapsed=None,
        time_remaining=time_remaining,
    )


def _texts(widget: PlanWidget) -> list[str]:
    """Return the text of every progress row, top to bottom."""
    assert widget.progress_group is not None
    labels = widget.progress_group.findChildren(QtW.QLabel, "progress-text")
    return [label.text() for label in labels]


class TestActionButton:
    """Tests for ActionButton."""

    def test_initial_label_is_capitalised_name(self) -> None:
        """Label the button with the action name, capitalised."""
        btn = ActionButton(PlanAction(name="go"))
        assert btn.text() == "Go"

    def test_tooltip_set_when_description_present(self) -> None:
        """Use the action description as the tooltip."""
        btn = ActionButton(PlanAction(name="go", description="Start acquisition"))
        assert btn.toolTip() == "Start acquisition"

    def test_not_checkable_for_a_clicked_action(self) -> None:
        """Make the button of a clicked action not checkable."""
        btn = ActionButton(PlanAction(name="go"))
        assert not btn.isCheckable()

    def test_checkable_for_an_action_with_toggle_states(self) -> None:
        """Make the button of an action with toggle states checkable."""
        btn = ActionButton(STREAM)
        assert btn.isCheckable()

    def test_label_updates_on_toggle(self) -> None:
        """Switch the button label between the two toggle states."""
        btn = ActionButton(STREAM)
        assert btn.text() == "Stream (Start)"
        btn.setChecked(True)
        assert btn.text() == "Stream (Stop)"
        btn.setChecked(False)
        assert btn.text() == "Stream (Start)"

    def test_release_shows_the_button_released_and_emits_nothing(self) -> None:
        """Uncheck the button on release without emitting toggled."""
        btn = ActionButton(STREAM)
        btn.setChecked(True)
        toggled: list[bool] = []
        btn.toggled.connect(toggled.append)

        btn.release()

        assert not btn.isChecked()
        assert btn.text() == "Stream (Start)"
        assert toggled == []


class TestCreatePlanWidget:
    """Tests for create_plan_widget output structure."""

    def test_simple_plan_has_no_pause_button(self) -> None:
        """Give a plain plan no pause button."""
        pw = create_plan_widget(_simple_spec())
        assert pw.pause_button is None

    def test_simple_plan_has_no_actions_group(self) -> None:
        """Give a plain plan no actions group and no action buttons."""
        pw = create_plan_widget(_simple_spec())
        assert pw.actions_group is None
        assert pw.action_buttons == {}

    def test_simple_plan_run_button_not_checkable(self) -> None:
        """Make the run button of a plain plan not checkable."""
        pw = create_plan_widget(_simple_spec())
        assert not pw.run_button.isCheckable()

    def test_continuous_plan_run_button_is_checkable(self) -> None:
        """Make the run button of a continuous plan checkable."""
        pw = create_plan_widget(_continuous_spec())
        assert pw.run_button.isCheckable()

    def test_continuous_plan_has_no_pause_button(self) -> None:
        """Give a continuous plan that cannot pause no pause button."""
        pw = create_plan_widget(_continuous_spec())
        assert pw.pause_button is None

    def test_pausable_plan_has_pause_button(self) -> None:
        """Give a pausable plan a pause button."""
        pw = create_plan_widget(_pausable_spec())
        assert pw.pause_button is not None

    def test_pausable_plan_pause_button_initially_disabled(self) -> None:
        """Disable the pause button until the plan runs."""
        pw = create_plan_widget(_pausable_spec())
        assert pw.pause_button is not None
        assert not pw.pause_button.isEnabled()

    def test_action_plan_has_actions_group(self) -> None:
        """Give a plan with an action parameter an actions group."""
        pw = create_plan_widget(_action_spec())
        assert pw.actions_group is not None

    def test_action_plan_actions_group_initially_disabled(self) -> None:
        """Disable the actions group until the plan runs."""
        pw = create_plan_widget(_action_spec())
        assert pw.actions_group is not None
        assert not pw.actions_group.isEnabled()

    def test_action_plan_has_action_button(self) -> None:
        """Add a button for the plan's action, keyed by its name."""
        pw = create_plan_widget(_action_spec())
        assert "snap" in pw.action_buttons

    def test_has_actions_true_when_actions_present(self) -> None:
        """Report has_actions for a plan with an action."""
        assert create_plan_widget(_action_spec()).has_actions()

    def test_has_actions_false_when_no_actions(self) -> None:
        """Report no actions for a plan without any."""
        assert not create_plan_widget(_simple_spec()).has_actions()

    def test_run_callback_connected(self) -> None:
        """Call run_callback when the run button of a plain plan is clicked."""
        fired: list[bool] = []
        pw = create_plan_widget(_simple_spec(), run_callback=lambda: fired.append(True))
        pw.run_button.click()
        assert fired == [True]

    def test_toggle_callback_connected(self) -> None:
        """Call toggle_callback when the run button of a continuous plan toggles."""
        states: list[bool] = []
        pw = create_plan_widget(
            _continuous_spec(), toggle_callback=lambda checked: states.append(checked)
        )
        pw.run_button.setChecked(True)
        assert True in states

    def test_parameters_returns_current_values(self) -> None:
        """Return the current parameter values by name."""
        assert create_plan_widget(_simple_spec()).parameters == {"frames": 1}

    def test_literal_param_in_parameters(self) -> None:
        """Return the selected value of a Literal parameter."""
        assert create_plan_widget(_literal_spec()).parameters == {"egu": "um"}

    def test_a_literal_of_integers_yields_an_integer(self) -> None:
        """Return an int, not a string, for a Literal of integers."""
        assert create_plan_widget(_int_literal_spec()).parameters == {"mode": 2}

    def test_a_bool_parameter_shows_its_name_once(self) -> None:
        """Show a bool parameter's name in its form row only, not on the checkbox."""
        pw = create_plan_widget(_bool_spec())
        checkbox = pw.group_box.findChild(QtW.QCheckBox)

        assert checkbox is not None
        # magicgui gives a CheckBox its name as text too, which rendered every bool
        # parameter as "write forever [ ] write forever".
        assert checkbox.text() == ""
        labels = [
            label.text()
            for label in pw.group_box.findChildren(QtW.QLabel)
            if label.text() == "write forever"
        ]
        assert labels == ["write forever"]
        assert pw.parameters == {"write_forever": False}

    def test_get_action_button_returns_button(self) -> None:
        """Return the ActionButton for a known action name."""
        pw = create_plan_widget(_action_spec())
        btn = pw.get_action_button("snap")
        assert btn is not None
        assert isinstance(btn, ActionButton)

    def test_get_action_button_returns_none_for_unknown(self) -> None:
        """Return None for an unknown action name."""
        pw = create_plan_widget(_action_spec())
        assert pw.get_action_button("nonexistent") is None


def _listed(pw: PlanWidget) -> list[str]:
    """Return every entry of the callbacks list, checked or not, in order."""
    assert pw.callbacks_list is not None
    items = map(pw.callbacks_list.item, range(pw.callbacks_list.count()))
    return [item.text() for item in items if item is not None]


class TestCallbacksList:
    """Tests for the document callbacks a plan widget offers."""

    @pytest.mark.parametrize(
        ("carried", "extendable", "listed"),
        [
            ((), True, ["a", "b", "c"]),
            (("b",), True, ["b", "a", "c"]),
            (("b",), False, ["b"]),
            (("own",), True, ["own", "a", "b", "c"]),
        ],
    )
    def test_the_plans_own_callbacks_are_listed_first(
        self, carried: tuple[str, ...], extendable: bool, listed: list[str]
    ) -> None:
        """List the plan's callbacks, then the catalogue's if extendable, once each."""
        pw = create_plan_widget(
            _simple_spec(),
            plan_callbacks=[CALLBACKS[name] for name in carried],
            extendable=extendable,
            available_callbacks=CATALOGUE,
        )
        assert _listed(pw) == listed
        assert pw.callbacks == [CALLBACKS[name] for name in listed]

    def test_a_plan_running_with_no_callbacks_has_no_list(self) -> None:
        """Show no callbacks list for a plan not extendable that carries none."""
        pw = create_plan_widget(
            _simple_spec(), extendable=False, available_callbacks=CATALOGUE
        )
        assert pw.callbacks_list is None
        assert pw.callbacks == []

    @pytest.mark.parametrize(
        ("attached", "expected"),
        [
            (None, ["a", "b", "c"]),
            (["c", "a"], ["c", "a"]),
            (["gone", "b"], ["b"]),
        ],
    )
    def test_a_previous_choice_is_restored(
        self, attached: list[str] | None, expected: list[str]
    ) -> None:
        """Restore the attached callbacks in the given order, dropping unknown names."""
        pw = create_plan_widget(
            _simple_spec(), available_callbacks=CATALOGUE, attached_callbacks=attached
        )
        assert pw.attached_callbacks == expected
        assert pw.callbacks == [CALLBACKS[name] for name in expected]

    def test_the_plans_own_callback_cannot_be_unchecked(self) -> None:
        """Make the plan's own callback uncheckable and omit it from attached names."""
        pw = create_plan_widget(
            _simple_spec(),
            plan_callbacks=[CALLBACKS["own"]],
            available_callbacks=CATALOGUE,
        )
        assert pw.callbacks_list is not None
        item = pw.callbacks_list.item(0)
        assert item is not None
        assert not item.flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable
        assert pw.attached_callbacks == ["a", "b", "c"]

    def test_unchecking_a_callback_reports_the_attached_names(self) -> None:
        """Report the remaining attached names when a callback is unchecked."""
        reported: list[list[str]] = []
        pw = create_plan_widget(
            _simple_spec(),
            available_callbacks=CATALOGUE,
            selection_callback=reported.append,
        )
        assert pw.callbacks_list is not None
        item = pw.callbacks_list.item(0)
        assert item is not None
        item.setCheckState(QtCore.Qt.CheckState.Unchecked)
        assert reported == [["b", "c"]]

    def test_a_callback_moved_above_the_plans_own_is_put_after_it(self) -> None:
        """Put a callback moved above the plan's own callback back after it."""
        reported: list[list[str]] = []
        pw = create_plan_widget(
            _simple_spec(),
            plan_callbacks=[CALLBACKS["own"]],
            available_callbacks=CATALOGUE,
            selection_callback=reported.append,
        )
        assert pw.callbacks_list is not None
        model = pw.callbacks_list.model()
        assert model is not None
        model.moveRow(QtCore.QModelIndex(), 3, QtCore.QModelIndex(), 0)
        assert _listed(pw) == ["own", "c", "a", "b"]
        assert reported[-1] == ["c", "a", "b"]


class TestPlanWidgetControlAPI:
    """Tests for PlanWidget.toggle / pause / setEnabled / enable_actions."""

    def test_toggle_swaps_the_run_button_text(self) -> None:
        """Switch the run button text between Run and Stop on toggle."""
        pw = create_plan_widget(_continuous_spec())
        pw.toggle(True)
        assert pw.run_button.text() == "Stop"
        pw.toggle(False)
        assert pw.run_button.text() == "Run"

    def test_toggle_off_releases_a_plan_that_ended_while_paused(self) -> None:
        """Reset the run and pause buttons, calling nothing, when a paused plan ends."""
        toggled: list[bool] = []
        paused: list[bool] = []
        pw = create_plan_widget(
            _pausable_spec(),
            toggle_callback=toggled.append,
            pause_callback=paused.append,
        )
        assert pw.pause_button is not None
        pw.run_button.click()
        pw.toggle(True)
        pw.pause_button.click()
        pw.pause(True)
        pw.toggle(False)
        assert toggled == [True]
        assert paused == [True]
        assert not pw.run_button.isChecked()
        assert pw.run_button.isEnabled()
        assert not pw.pause_button.isChecked()
        assert pw.pause_button.text() == "Pause"

    def test_toggle_enables_the_pause_button_while_running(self) -> None:
        """Enable the pause button only while the plan runs."""
        pw = create_plan_widget(_pausable_spec())
        assert pw.pause_button is not None
        pw.toggle(True)
        assert pw.pause_button.isEnabled()
        pw.toggle(False)
        assert not pw.pause_button.isEnabled()

    def test_toggle_freezes_the_parameters_while_running(self) -> None:
        """Disable the parameter inputs while the plan runs."""
        pw = create_plan_widget(_simple_spec())
        pw.toggle(True)
        assert not pw.params_widget.isEnabled()
        pw.toggle(False)
        assert pw.params_widget.isEnabled()

    def test_toggle_enables_actions_group(self) -> None:
        """Enable the actions group when the plan starts."""
        pw = create_plan_widget(_action_spec())
        pw.toggle(True)
        assert pw.actions_group is not None
        assert pw.actions_group.isEnabled()

    def test_pause_swaps_the_pause_button_text(self) -> None:
        """Switch the pause button text between Pause and Resume."""
        pw = create_plan_widget(_pausable_spec())
        assert pw.pause_button is not None
        pw.toggle(True)
        pw.pause(True)
        assert pw.pause_button.text() == "Resume"
        pw.pause(False)
        assert pw.pause_button.text() == "Pause"

    def test_a_paused_plan_can_be_stopped(self) -> None:
        """Keep the stop button enabled while the plan is paused, and report its press."""
        toggled: list[bool] = []
        pw = create_plan_widget(_pausable_spec(), toggle_callback=toggled.append)
        pw.run_button.click()
        pw.toggle(True)
        pw.pause(True)
        assert pw.run_button.isEnabled()
        pw.run_button.click()
        assert toggled == [True, False]

    def test_set_enabled_reaches_the_group_box(self) -> None:
        """Apply setEnabled to the group box."""
        pw = create_plan_widget(_simple_spec())
        pw.setEnabled(False)
        assert not pw.group_box.isEnabled()
        pw.setEnabled(True)
        assert pw.group_box.isEnabled()

    def test_enable_actions_reaches_the_actions_group(self) -> None:
        """Apply enable_actions to the actions group."""
        pw = create_plan_widget(_action_spec())
        assert pw.actions_group is not None
        pw.enable_actions(True)
        assert pw.actions_group.isEnabled()
        pw.enable_actions(False)
        assert not pw.actions_group.isEnabled()

    def test_enable_actions_noop_when_no_actions(self) -> None:
        """Accept enable_actions without error when the plan has no actions."""
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
    """Accept a parameter type in a plan only when the Qt view can build its widget."""
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

    def plan(x: object) -> MsgGenerator[None]:
        yield from ()

    plan.__annotations__["x"] = annotation
    try:
        create_plan_spec(plan, {})
    except UnresolvableAnnotationError:
        accepted = False
    else:
        accepted = True

    assert accepted is renderable


@pytest.mark.parametrize(
    ("scope", "busy", "text"),
    [
        (_scope("s", current=37, target=100, fraction=0.37), False, "37 / 100 frames"),
        (_scope("s", fraction=0.42), False, "42 %"),
        (_scope("s", current=412), True, "412 frames"),
        (_scope("s", unit=""), True, ""),
        (
            _scope("s", current=3.5, target=10, fraction=0.35, precision=1),
            False,
            "3.5 / 10.0 frames",
        ),
        (
            _scope("s", current=1, target=4, fraction=0.25, time_remaining=12.4),
            False,
            "1 / 4 frames, 12 s left",
        ),
    ],
    ids=["counted", "fraction", "no end", "nothing yet", "precision", "time left"],
)
def test_a_scope_shows_a_bar_and_what_it_counts(
    scope: ProgressState, busy: bool, text: str
) -> None:
    """Fill a bar from a known fraction, or keep it busy, and say what is counted."""
    widget = create_plan_widget(_simple_spec())
    assert widget.progress_group is not None

    widget.show_progress((scope,))

    bar = widget.progress_group.findChildren(QtW.QProgressBar)[0]
    assert (bar.maximum() == 0) is busy
    if not busy:
        assert scope.fraction is not None
        assert bar.value() == round(scope.fraction * bar.maximum())
    assert _texts(widget) == [text]
    assert not widget.progress_group.isHidden()


def test_a_nested_scope_is_indented_and_a_finished_one_removed() -> None:
    """Indent a child under its parent, drop a finished row, and hide on nothing."""
    widget = create_plan_widget(_simple_spec())
    assert widget.progress_group is not None
    outer = _scope("repeats", current=1, target=3, fraction=1 / 3, unit="repeats")
    inner = _scope("series", parent="repeats", current=4, target=10, fraction=0.4)

    widget.show_progress((outer, inner))
    names = widget.progress_group.findChildren(QtW.QLabel, "progress-name")
    indents = {label.text(): label.indent() for label in names}
    assert indents["series"] > indents["repeats"]

    widget.show_progress((outer,))
    assert _texts(widget) == ["1 / 3 repeats"]

    widget.show_progress(())
    assert widget.progress_group.isHidden()


def test_progress_rows_follow_the_order_of_the_scopes() -> None:
    """Keep a row per scope in the order given, and update values in place."""
    widget = create_plan_widget(_simple_spec())
    assert widget.progress_group is not None
    layout = widget.progress_group.layout()
    assert isinstance(layout, QtW.QGridLayout)

    def rows() -> list[tuple[str, str]]:
        """Return each row's name and text, top to bottom."""
        found = []
        for row in range(layout.rowCount()):
            name, text = layout.itemAtPosition(row, 0), layout.itemAtPosition(row, 2)
            if name is None or text is None:
                continue
            name_label, text_label = name.widget(), text.widget()
            assert isinstance(name_label, QtW.QLabel)
            assert isinstance(text_label, QtW.QLabel)
            found.append((name_label.text(), text_label.text()))
        return found

    first = _scope("first", current=1, target=4, fraction=0.25)
    second = _scope("second", current=2, target=4, fraction=0.5)
    widget.show_progress((first, second))
    widget.show_progress((second, first))
    assert rows() == [("second", "2 / 4 frames"), ("first", "1 / 4 frames")]

    widget.show_progress((second, _scope("first", current=3, target=4, fraction=0.75)))
    assert rows() == [("second", "2 / 4 frames"), ("first", "3 / 4 frames")]


def test_a_new_page_hides_its_progress() -> None:
    """Hide the progress group of a page whose plan has reported nothing."""
    widget = create_plan_widget(_simple_spec())
    assert widget.progress_group is not None
    assert widget.progress_group.isHidden()
