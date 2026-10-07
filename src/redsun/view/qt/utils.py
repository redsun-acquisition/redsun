"""Qt widgets for interfaces that run plans.

- `ActionButton`: a `QPushButton` carrying a `PlanAction`, its label following
  the toggle state.
- `PlanWidget`: a frozen dataclass owning one plan's widgets (parameter form,
  run and pause buttons, action buttons).
- `create_plan_widget`: builds a `PlanWidget` from a `PlanSpec` and connects
  the given callbacks.
- `PlanInfoDialog`: a dialog rendering a plan's docstring as Markdown.
- `create_param_widget`: re-exported from `_widget_factory`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import magicgui.widgets as mgw
import magicgui.widgets.bases as mgw_bases
from qtpy import QtCore
from qtpy import QtWidgets as QtW

from redsun.engine.actions import PlanAction
from redsun.presenter.plan_spec import ParamKind

from ._value_widgets import located, problems_of
from ._widget_factory import create_param_widget

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from redsun.engine import ProgressState
    from redsun.presenter.plan_spec import PlanSpec
    from redsun.registry import CallbackType

__all__ = [
    "ActionButton",
    "PlanInfoDialog",
    "PlanWidget",
    "create_param_widget",
    "create_plan_widget",
]

_PROGRESS_STEPS = 1000
"""Steps of a progress bar with a known end."""

_PROGRESS_INDENT = 16
"""Pixels a progress row is indented per scope it is nested under."""


class ActionButton(QtW.QPushButton):
    """A `QPushButton` carrying a `PlanAction`.

    Its label follows the toggle state, using the action's `toggle_states`.

    Parameters
    ----------
    action
        The button's action.
    parent
        The parent widget.

    Attributes
    ----------
    action : PlanAction
        The button's action.
    """

    def __init__(self, action: PlanAction, parent: QtW.QWidget | None = None) -> None:
        self.name_capital = action.name.capitalize()
        super().__init__(self.name_capital, parent)
        self.action = action

        if action.description:
            self.setToolTip(action.description)

        if action.toggle_states is not None:
            self.setCheckable(True)
            self.toggled.connect(self._update_text)
            self._update_text(False)

    def release(self) -> None:
        """Show the button released, without emitting `toggled`.

        For an action that ended by itself: unchecking the button any other
        way reads as the user asking the action to end.
        """
        with QtCore.QSignalBlocker(self):
            self.setChecked(False)
        self._update_text(False)

    def _update_text(self, checked: bool) -> None:
        """Update the label to the toggle state."""
        states = self.action.toggle_states
        if states is not None:
            self.setText(f"{self.name_capital} ({states[1] if checked else states[0]})")


@dataclass(frozen=True)
class PlanWidget:
    """The Qt widgets of one plan."""

    spec: PlanSpec
    """The plan's specification."""

    group_box: QtW.QWidget
    """The top-level page, for a QStackedWidget."""

    run_button: QtW.QPushButton
    """The button running or stopping the plan."""

    container: mgw.Container[mgw_bases.ValueWidget[Any]]
    """The `magicgui` Container of parameter widgets."""

    device_widgets: list[mgw_bases.ValueWidget[Any]]
    """Device parameter widgets (`DeviceSequenceEdit` or `ComboBox`), in the *Devices* group."""

    params_widget: QtW.QWidget
    """Widget holding devices_group and params_group; disabling it locks every
    parameter input but not the run, stop and pause buttons.
    """

    problem_label: QtW.QLabel
    """The first of `problems`, under the parameters; hidden while there is none."""

    action_buttons: dict[str, ActionButton]
    """Action buttons by action name."""

    actions_group: QtW.QGroupBox | None = None
    """The group box of action buttons, or None if the plan has no actions."""

    pause_button: QtW.QPushButton | None = None
    """The pause/resume button, or None if the plan is not pausable."""

    callbacks_list: QtW.QListWidget | None = None
    """The document callbacks to run the plan with, or None if it runs with none.

    The callbacks the plan requires come first, checked and fixed in place; the
    rest can be checked and dragged into a different order.
    """

    progress_group: QtW.QGroupBox | None = None
    """The "Progress" group of the page, hidden until the plan reports a scope."""

    _progress_rows: dict[str, tuple[QtW.QLabel, QtW.QProgressBar, QtW.QLabel]] = field(
        default_factory=dict, init=False, repr=False
    )
    _progress_order: list[str] = field(default_factory=list, init=False, repr=False)

    def toggle(self, status: bool) -> None:
        """Update the widgets when a continuous plan starts or stops.

        The run and pause buttons are set to match *status* without emitting
        `toggled`, so a plan that ended by itself can be shown as stopped.

        Parameters
        ----------
        status
            `True` when the plan is starting; `False` when stopping.
        """
        with QtCore.QSignalBlocker(self.run_button):
            self.run_button.setChecked(status)
        self.run_button.setText("Stop" if status else "Run")
        if self.pause_button:
            if not status:
                with QtCore.QSignalBlocker(self.pause_button):
                    self.pause_button.setChecked(False)
                self.pause_button.setText("Pause")
            self.pause_button.setEnabled(status)
        if self.actions_group:
            self.actions_group.setEnabled(status)
        self.params_widget.setEnabled(not status)
        if status:
            self.run_button.setEnabled(True)
        else:
            self._check()

    def pause(self, status: bool) -> None:
        """Update the widgets when a plan pauses or resumes.

        The stop button stays enabled, so a paused plan can be stopped.

        Parameters
        ----------
        status
            `True` when pausing; `False` when resuming.
        """
        if self.pause_button:
            self.pause_button.setText("Resume" if status else "Pause")

    def setEnabled(self, enabled: bool) -> None:
        """Enable or disable the whole plan widget.

        Enabling it enables Run only while `problems` is empty.

        Parameters
        ----------
        enabled
            `True` to enable; `False` to disable.
        """
        self.group_box.setEnabled(enabled)
        self.params_widget.setEnabled(enabled)
        if enabled:
            self._check()
        else:
            self.run_button.setEnabled(False)

    def enable_actions(self, enabled: bool = True) -> None:
        """Enable or disable the actions group box.

        Parameters
        ----------
        enabled
            `True` to enable; `False` to disable.
        """
        if self.actions_group:
            self.actions_group.setEnabled(enabled)

    def get_action_button(self, action_name: str) -> ActionButton | None:
        """Return the `ActionButton` for `action_name`, or `None` if absent.

        Parameters
        ----------
        action_name
            The name of the action.
        """
        return self.action_buttons.get(action_name)

    def has_actions(self) -> bool:
        """Return `True` if the plan has an action button."""
        return bool(self.action_buttons)

    @property
    def problems(self) -> list[str]:
        """Why the plan cannot run, one line per invalid input, prefixed with its parameter.

        An input's own problems come first; only an input with none is checked
        against its parameter's limits. Run stays disabled while the list is
        not empty.
        """
        described = {p.name: p for p in self.spec.parameters}
        found: list[str] = []
        for w in self.container:
            own = [located(w.name, problem) for problem in problems_of(w)]
            if not own and w.name in described:
                own = described[w.name].problems(w.value)
            found.extend(own)
        return found

    def _check(self) -> None:
        problems = self.problems
        self.problem_label.setText(problems[0] if problems else "")
        self.problem_label.setVisible(bool(problems))
        # parameters are disabled while a plan runs, and Run is its Stop then
        if self.params_widget.isEnabled():
            self.run_button.setEnabled(not problems)

    @property
    def parameters(self) -> dict[str, Any]:
        """Current parameter values by name.

        The presenter turns them into positional and keyword arguments with
        `collect_arguments` / `resolve_arguments`.
        """
        return {w.name: w.value for w in self.container}

    @property
    def callbacks(self) -> list[CallbackType]:
        """The checked document callbacks, in the order the run uses."""
        return [
            item.data(QtCore.Qt.ItemDataRole.UserRole)
            for item in _checked(self.callbacks_list)
        ]

    @property
    def attached_callbacks(self) -> list[str]:
        """Names of the checked callbacks the user attached, in order."""
        return _attached(self.callbacks_list)

    def show_progress(self, scopes: Sequence[ProgressState]) -> None:
        """Show a row for each progress scope of the running plan, in the order given.

        A scope is indented under its parent, and a bar is busy while its
        scope has no known end. An empty *scopes* hides the group.
        """
        group = self.progress_group
        if group is None:
            return
        layout = cast("QtW.QGridLayout", group.layout())
        current = {scope.name for scope in scopes}
        for name in [name for name in self._progress_rows if name not in current]:
            for widget in self._progress_rows.pop(name):
                layout.removeWidget(widget)
                # deleteLater waits for the event loop; until then the row
                # would still be a child of the group
                widget.setParent(None)
                widget.deleteLater()
        order = [scope.name for scope in scopes]
        # an update to the same scopes only changes values: placing the rows
        # again is needed only when the scopes or their order changed
        placed = order == self._progress_order
        self._progress_order[:] = order
        depths: dict[str, int] = {}
        for row, scope in enumerate(scopes):
            depths[scope.name] = (
                depths.get(scope.parent, -1) + 1 if scope.parent is not None else 0
            )
            if scope.name not in self._progress_rows:
                name_label = QtW.QLabel(scope.name)
                name_label.setObjectName("progress-name")
                bar = QtW.QProgressBar()
                bar.setTextVisible(False)
                text_label = QtW.QLabel()
                text_label.setObjectName("progress-text")
                self._progress_rows[scope.name] = (name_label, bar, text_label)
            name_label, bar, text_label = self._progress_rows[scope.name]
            if not placed:
                for column, cell in enumerate((name_label, bar, text_label)):
                    layout.removeWidget(cell)
                    layout.addWidget(cell, row, column)
            name_label.setIndent(depths[scope.name] * _PROGRESS_INDENT)
            if scope.fraction is None:
                bar.setRange(0, 0)
            else:
                bar.setRange(0, _PROGRESS_STEPS)
                bar.setValue(round(scope.fraction * _PROGRESS_STEPS))
            text_label.setText(_progress_text(scope))
        group.setHidden(not scopes)


def _checked(callbacks_list: QtW.QListWidget | None) -> list[QtW.QListWidgetItem]:
    """Return the checked rows of *callbacks_list*, in order."""
    if callbacks_list is None:
        return []
    items = (callbacks_list.item(row) for row in range(callbacks_list.count()))
    return [
        item
        for item in items
        if item is not None and item.checkState() == QtCore.Qt.CheckState.Checked
    ]


def _attached(callbacks_list: QtW.QListWidget | None) -> list[str]:
    """Return the names of the checked rows the user may uncheck, in order."""
    return [
        item.text()
        for item in _checked(callbacks_list)
        if item.flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable
    ]


def _build_param_widgets(
    spec: PlanSpec,
) -> tuple[list[mgw_bases.ValueWidget[Any]], list[mgw_bases.ValueWidget[Any]]]:
    """Split *spec*'s parameters into device widgets and plain parameter widgets.

    Device widgets cover `Sequence[PDevice]`, `Set[PDevice]`,
    `*args: PDevice` and `PDevice` parameters; scalars, Literals and the
    rest are plain parameters. Each list holds one `magicgui` widget per
    parameter, in signature order.
    """
    device_widgets: list[mgw_bases.ValueWidget[Any]] = []
    param_widgets: list[mgw_bases.ValueWidget[Any]] = []

    for p in spec.parameters:
        if p.hidden or p.actions is not None:
            continue
        if p.kind is ParamKind.VAR_KEYWORD:
            continue
        w = cast("mgw_bases.ValueWidget[Any]", create_param_widget(p))
        # device_proto is set by plan_spec for all PDevice-backed params
        if p.device_proto is not None:
            device_widgets.append(w)
        else:
            param_widgets.append(w)

    return device_widgets, param_widgets


def _build_devices_group(
    device_widgets: list[mgw_bases.ValueWidget[Any]],
) -> QtW.QGroupBox | None:
    """Build the *Devices* group box.

    Each device parameter gets a titled group box holding its widget, a
    `DeviceSequenceEdit` for several devices or a `ComboBox` for one.
    Returns `None` without device parameters.
    """
    if not device_widgets:
        return None

    devices_group = QtW.QGroupBox("Devices")
    devices_layout = QtW.QVBoxLayout(devices_group)
    devices_layout.setContentsMargins(4, 4, 4, 4)
    devices_layout.setSpacing(4)

    for w in device_widgets:
        label_text: str = getattr(w, "label", w.name)
        sub_group = QtW.QGroupBox(label_text)
        sub_layout = QtW.QVBoxLayout(sub_group)
        sub_layout.setContentsMargins(4, 20, 4, 4)
        native: QtW.QWidget = w.native
        sub_layout.addWidget(native)
        devices_layout.addWidget(sub_group)

    return devices_group


def _build_params_group(
    param_widgets: list[mgw_bases.ValueWidget[Any]],
) -> QtW.QGroupBox | None:
    """Build the *Parameters* group box using a `QFormLayout`.

    Each plain parameter is a labelled form row. Returns `None` without plain
    parameters.
    """
    if not param_widgets:
        return None

    params_group = QtW.QGroupBox("Parameters")
    params_form = QtW.QFormLayout(params_group)
    params_form.setContentsMargins(4, 6, 4, 4)

    for w in param_widgets:
        native: QtW.QWidget = w.native
        label_text: str = getattr(w, "label", w.name)
        # magicgui gives a CheckBox its name as text too, and the form row
        # already carries it as the label
        if isinstance(w, mgw.CheckBox):
            w.text = ""
        params_form.addRow(label_text, native)

    return params_group


def _format_number(value: float, precision: int | None) -> str:
    """Return *value* with *precision* decimals, or in its shortest form."""
    return f"{value:.{precision}f}" if precision is not None else f"{value:g}"


def _progress_text(scope: ProgressState) -> str:
    """Return what a progress row says: a count against its end, a percentage, or a count."""
    if (
        scope.fraction is not None
        and scope.current is not None
        and scope.target is not None
    ):
        text = (
            f"{_format_number(scope.current, scope.precision)} / "
            f"{_format_number(scope.target, scope.precision)} {scope.unit}"
        )
    elif scope.fraction is not None:
        text = f"{round(scope.fraction * 100)} %"
    elif scope.current is not None:
        text = f"{_format_number(scope.current, scope.precision)} {scope.unit}"
    else:
        text = scope.unit
    if scope.time_remaining is not None:
        left = f"{scope.time_remaining:.0f} s left"
        text = f"{text}, {left}" if text else left
    return text


def _build_run_buttons(
    spec: PlanSpec,
    parent: QtW.QWidget,
    page_layout: QtW.QVBoxLayout,
    run_callback: Callable[[], None],
    toggle_callback: Callable[[bool], None],
    pause_callback: Callable[[bool], None],
) -> tuple[QtW.QPushButton, QtW.QPushButton | None]:
    """Add the run button, and the pause button if needed, to *page_layout*."""
    run_layout = QtW.QHBoxLayout()
    run_container = QtW.QWidget(parent)

    run_button = QtW.QPushButton("Run")
    if spec.continuous:
        run_button.setCheckable(True)
        run_button.toggled.connect(toggle_callback)
    else:
        run_button.clicked.connect(run_callback)
    run_layout.addWidget(run_button)

    pause_button: QtW.QPushButton | None = None
    if spec.pausable:
        pause_button = QtW.QPushButton("Pause")
        pause_button.setEnabled(False)
        pause_button.setCheckable(True)
        pause_button.toggled.connect(pause_callback)
        run_layout.addWidget(pause_button)

    run_container.setLayout(run_layout)
    page_layout.addWidget(run_container)
    return run_button, pause_button


def _build_actions_group(
    spec: PlanSpec,
    page_layout: QtW.QVBoxLayout,
    action_clicked_callback: Callable[[str], None],
    action_toggled_callback: Callable[[bool, str], None],
) -> tuple[QtW.QGroupBox | None, dict[str, ActionButton]]:
    """Add the actions group box to *page_layout*, if the plan has actions."""
    actions = [
        action
        for p in spec.parameters
        if p.actions is not None
        for action in ([p.actions] if isinstance(p.actions, PlanAction) else p.actions)
    ]
    if not actions:
        return None, {}

    actions_group = QtW.QGroupBox("Actions")
    actions_layout = QtW.QHBoxLayout(actions_group)
    actions_group.setEnabled(False)

    action_buttons: dict[str, ActionButton] = {}
    for action in actions:
        btn = ActionButton(action)
        if action.toggle_states is not None:
            btn.toggled.connect(
                lambda checked, name=action.name: action_toggled_callback(checked, name)
            )
        else:
            btn.clicked.connect(
                lambda _, name=action.name: action_clicked_callback(name)
            )
        action_buttons[action.name] = btn
        actions_layout.addWidget(btn)

    page_layout.addWidget(actions_group)
    return actions_group, action_buttons


def _label(callback: CallbackType, available: Mapping[str, CallbackType]) -> str:
    """Return the name *callback* has in *available*, or one it carries."""
    for name, entry in available.items():
        if entry is callback:
            return name
    return str(getattr(callback, "name", type(callback).__name__))


def _build_callbacks_group(
    params_layout: QtW.QVBoxLayout,
    own: Sequence[CallbackType],
    extendable: bool,
    available: Mapping[str, CallbackType],
    attached: Sequence[str] | None,
    selection_callback: Callable[[list[str]], None],
) -> QtW.QListWidget | None:
    """Build the *Callbacks* group box and add it to *params_layout* if needed.

    Returns `None` when the plan carries no callback and the user may attach
    none.
    """
    optional = (
        {
            name: entry
            for name, entry in available.items()
            if all(entry is not carried for carried in own)
        }
        if extendable
        else {}
    )
    if not own and not optional:
        return None
    order = list(optional)
    if attached is not None:
        chosen = [name for name in attached if name in optional]
        order = chosen + [name for name in optional if name not in chosen]

    flags = QtCore.Qt.ItemFlag
    role = QtCore.Qt.ItemDataRole.UserRole
    checked, unchecked = QtCore.Qt.CheckState.Checked, QtCore.Qt.CheckState.Unchecked
    callbacks_list = QtW.QListWidget()
    callbacks_list.setDragDropMode(QtW.QAbstractItemView.DragDropMode.InternalMove)
    pinned: list[QtW.QListWidgetItem] = []
    for callback in own:
        item = QtW.QListWidgetItem(_label(callback, available))
        item.setData(role, callback)
        item.setFlags(flags.ItemIsEnabled)
        item.setCheckState(checked)
        item.setToolTip("Required by the plan")
        callbacks_list.addItem(item)
        pinned.append(item)
    for name in order:
        item = QtW.QListWidgetItem(name)
        item.setData(role, optional[name])
        item.setFlags(
            flags.ItemIsEnabled
            | flags.ItemIsSelectable
            | flags.ItemIsUserCheckable
            | flags.ItemIsDragEnabled
        )
        item.setCheckState(
            checked if attached is None or name in attached else unchecked
        )
        callbacks_list.addItem(item)

    def keep_own_first() -> None:
        # a drop may land above the plan's own callbacks, which run first
        # whatever the list shows, so the rows are put back to match
        for row, item in enumerate(pinned):
            current = callbacks_list.row(item)
            if current != row and model is not None:
                model.moveRow(QtCore.QModelIndex(), current, QtCore.QModelIndex(), row)

    def notify() -> None:
        selection_callback(_attached(callbacks_list))

    model = callbacks_list.model()
    if model is not None:
        model.rowsMoved.connect(keep_own_first)
        model.rowsMoved.connect(notify)
    callbacks_list.itemChanged.connect(notify)

    group = QtW.QGroupBox("Callbacks")
    layout = QtW.QVBoxLayout(group)
    layout.setContentsMargins(4, 6, 4, 4)
    layout.addWidget(callbacks_list)
    params_layout.addWidget(group)
    return callbacks_list


def create_plan_widget(
    spec: PlanSpec,
    run_callback: Callable[[], None] | None = None,
    toggle_callback: Callable[[bool], None] | None = None,
    pause_callback: Callable[[bool], None] | None = None,
    action_clicked_callback: Callable[[str], None] | None = None,
    action_toggled_callback: Callable[[bool, str], None] | None = None,
    plan_callbacks: Sequence[CallbackType] = (),
    extendable: bool = True,
    available_callbacks: Mapping[str, CallbackType] | None = None,
    attached_callbacks: Sequence[str] | None = None,
    selection_callback: Callable[[list[str]], None] | None = None,
) -> PlanWidget:
    """Build a complete `PlanWidget` for *spec*.

    Run stays disabled while an input holds an invalid value; see
    `PlanWidget.problems`.

    Parameters
    ----------
    spec
        The plan's specification.
    run_callback
        Connected to `run_button.clicked` for plans that are not continuous.
    toggle_callback
        Connected to `run_button.toggled` for continuous plans.
    pause_callback
        Connected to `pause_button.toggled` for pausable plans.
    action_clicked_callback
        Called with `action_name` when an action's button is clicked.
    action_toggled_callback
        Called with `(checked, action_name)` when an action's button is
        pressed or released.
    plan_callbacks
        The document callbacks the plan requires, in the order they run. They
        are listed first, checked, and cannot be unchecked or moved.
    extendable
        Whether the user may attach callbacks after *plan_callbacks*.
    available_callbacks
        The document callbacks the user may attach, by the name each row is
        labelled with, in the order offered. Ignored when *extendable* is
        `False`.
    attached_callbacks
        Names the user attached before, in their order. The other available
        callbacks are listed unchecked after them, and a name not available is
        ignored. `None` checks every available callback.
    selection_callback
        Called with `PlanWidget.attached_callbacks` when the user checks,
        unchecks or moves a callback.
    """
    page = QtW.QWidget()
    page_layout = QtW.QVBoxLayout(page)
    page_layout.setContentsMargins(4, 4, 4, 4)
    page_layout.setSpacing(4)

    device_widgets, param_widgets = _build_param_widgets(spec)

    # a flat list is what keeps `Container.parameters` reachable
    all_widgets = device_widgets + param_widgets
    container = mgw.Container(widgets=all_widgets)

    devices_group = _build_devices_group(device_widgets)
    params_group = _build_params_group(param_widgets)

    params_widget = QtW.QWidget()
    params_layout = QtW.QVBoxLayout(params_widget)
    params_layout.setContentsMargins(0, 0, 0, 0)
    params_layout.setSpacing(4)
    if devices_group is not None:
        params_layout.addWidget(devices_group)
    if params_group is not None:
        params_layout.addWidget(params_group)
    callbacks_list = _build_callbacks_group(
        params_layout,
        plan_callbacks,
        extendable,
        available_callbacks or {},
        attached_callbacks,
        selection_callback or (lambda names: None),
    )
    page_layout.addWidget(params_widget)

    problem_label = QtW.QLabel()
    problem_label.setWordWrap(True)
    problem_label.hide()
    page_layout.addWidget(problem_label)

    run_button, pause_button = _build_run_buttons(
        spec,
        page,
        page_layout,
        run_callback or (lambda: None),
        toggle_callback or (lambda checked: None),
        pause_callback or (lambda paused: None),
    )

    actions_group, action_buttons = _build_actions_group(
        spec,
        page_layout,
        action_clicked_callback or (lambda name: None),
        action_toggled_callback or (lambda checked, name: None),
    )

    progress_group = QtW.QGroupBox("Progress")
    progress_layout = QtW.QGridLayout(progress_group)
    progress_layout.setColumnStretch(1, 1)
    progress_group.hide()
    page_layout.addWidget(progress_group)

    widget = PlanWidget(
        spec=spec,
        group_box=page,
        run_button=run_button,
        pause_button=pause_button,
        container=container,
        device_widgets=device_widgets,
        params_widget=params_widget,
        problem_label=problem_label,
        actions_group=actions_group,
        action_buttons=action_buttons,
        callbacks_list=callbacks_list,
        progress_group=progress_group,
    )
    for w in container:
        w.changed.connect(lambda _value: widget._check())
    widget._check()
    return widget


class PlanInfoDialog(QtW.QDialog):
    """Dialog showing information to the user.

    Parameters
    ----------
    title
        The title of the dialog window.
    text
        Text shown, rendered as Markdown.
    parent
        The parent widget.
    """

    def __init__(
        self,
        title: str,
        text: str,
        parent: QtW.QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle(title)
        self.resize(500, 300)

        layout = QtW.QVBoxLayout(self)

        self.text_edit = QtW.QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMarkdown(text)
        layout.addWidget(self.text_edit)

        self.ok_button = QtW.QPushButton("OK")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self.accept)

        button_layout = QtW.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    @classmethod
    def show_dialog(
        cls, title: str, text: str, parent: QtW.QWidget | None = None
    ) -> int:
        """Create and show the dialog, and return `QDialog.Accepted` or `QDialog.Rejected`."""
        dialog = cls(title, text, parent)
        return dialog.exec()
