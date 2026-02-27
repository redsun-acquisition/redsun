"""Qt widget utilities for plan-based UIs.

This module provides the building blocks for a plan parameter form:

- `ActionButton` — a `QPushButton` that carries `Action` metadata and
  auto-updates its label when toggled.
- `PlanWidget` — a frozen dataclass owning all Qt widgets for a single
  plan (parameter form, run/pause buttons, action buttons).
- `create_plan_widget` — factory that builds a complete `PlanWidget` from
  a `PlanSpec` and wires up the caller-supplied callbacks.
- `PlanInfoDialog` — a simple Markdown-rendering dialog for displaying the plan docstring (if available).
- `create_param_widget` — re-exported from `_widget_factory` for convenience.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import magicgui.widgets as mgw
import magicgui.widgets.bases as mgw_bases
from qtpy import QtWidgets as QtW

from redsun.engine.actions import Action
from redsun.presenter.plan_spec import ParamKind
from redsun.presenter.utils import isdevice, isdevicesequence, isdeviceset
from redsun.view.qt._widget_factory import create_param_widget

if TYPE_CHECKING:
    from collections.abc import Callable

    from redsun.presenter.plan_spec import PlanSpec

__all__ = [
    "ActionButton",
    "PlanWidget",
    "PlanInfoDialog",
    "create_plan_widget",
    "create_param_widget",
]


class ActionButton(QtW.QPushButton):
    """A ``QPushButton`` that carries ``Action`` metadata.

    Automatically updates its label based on toggle state using the action's
    ``toggle_states`` attribute.

    Parameters
    ----------
    action : Action
        The action to associate with this button.
    parent : QtWidgets.QWidget | None, optional
        The parent widget. Default is ``None``.

    Attributes
    ----------
    action : Action
        The action associated with this button.
    """

    def __init__(self, action: Action, parent: QtW.QWidget | None = None) -> None:
        self.name_capital = action.name.capitalize()
        super().__init__(self.name_capital, parent)
        self.action = action

        if action.description:
            self.setToolTip(action.description)

        if action.togglable:
            self.setCheckable(True)
            self.toggled.connect(self._update_text)
            self._update_text(False)

    def _update_text(self, checked: bool) -> None:
        """Update button text based on toggle state."""
        state_text = (
            self.action.toggle_states[1] if checked else self.action.toggle_states[0]
        )
        self.setText(f"{self.name_capital} ({state_text})")


@dataclass(frozen=True)
class PlanWidget:
    """Container for all Qt widgets that represent a single plan."""

    spec: PlanSpec
    """The plan specification that this widget represents."""

    group_box: QtW.QWidget
    """The top-level page widget suitable for stacking in a QStackedWidget."""

    run_button: QtW.QPushButton
    """The button to run (or stop) the plan."""

    container: mgw.Container[mgw_bases.ValueWidget[Any]]
    """The magicgui Container holding the parameter input widgets."""

    action_buttons: dict[str, ActionButton]
    """Mapping of action names to their buttons for direct access."""

    actions_group: QtW.QGroupBox | None = None
    """The group box containing action buttons, or None if the plan has no actions."""

    pause_button: QtW.QPushButton | None = None
    """The pause/resume button, or None if the plan is not pausable."""

    def toggle(self, status: bool) -> None:
        """Update UI state when a togglable plan starts or stops.

        Parameters
        ----------
        status : bool
            `True` when the plan is starting; `False` when stopping.
        """
        self.run_button.setText("Stop" if status else "Run")
        if self.pause_button:
            self.pause_button.setEnabled(status)
        if self.actions_group:
            self.actions_group.setEnabled(status)
        self.container.enabled = not status

    def pause(self, status: bool) -> None:
        """Update UI state when a plan is paused or resumed.

        Parameters
        ----------
        status : bool
            `True` when pausing; `False` when resuming.
        """
        if self.pause_button:
            self.pause_button.setText("Resume" if status else "Pause")
            self.run_button.setEnabled(not status)

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        """Enable or disable the entire plan widget.

        Parameters
        ----------
        enabled : bool
            ``True`` to enable; ``False`` to disable.
        """
        self.group_box.setEnabled(enabled)
        self.run_button.setEnabled(enabled)
        self.container.enabled = enabled

    def enable_actions(self, enabled: bool = True) -> None:
        """Enable or disable the actions group box.

        Parameters
        ----------
        enabled : bool, optional
            ``True`` to enable; ``False`` to disable. Default is ``True``.
        """
        if self.actions_group:
            self.actions_group.setEnabled(enabled)

    def get_action_button(self, action_name: str) -> ActionButton | None:
        """Return the `ActionButton` for `action_name`, or `None` if absent.

        Parameters
        ----------
        action_name : str
            The name of the action.
        """
        return self.action_buttons.get(action_name)

    def has_actions(self) -> bool:
        """Return `True` if this plan has at least one action button."""
        return bool(self.action_buttons)

    @property
    def parameters(self) -> dict[str, Any]:
        """Current parameter values keyed by parameter name.

        The presenter is responsible for routing these into positional args
        and keyword args via ``collect_arguments`` / ``resolve_arguments``.
        """
        return {w.name: w.value for w in self.container}


def _build_param_widgets(
    spec: PlanSpec,
) -> tuple[
    list[mgw_bases.ValueWidget[Any]],  # device widgets (multiselect or single)
    list[mgw_bases.ValueWidget[Any]],  # plain parameter widgets
]:
    """Arrange *spec* parameters into device widgets and plain parameter widgets.

    Device widgets cover ``Sequence[PDevice]``, ``Set[PDevice]``, ``*args: PDevice``
    and bare ``PDevice`` parameters.  Everything else (scalars, Literals, …) goes
    into the plain parameters list.

    Returns
    -------
    device_widgets : list
        One magicgui widget per device parameter, in signature order.
    param_widgets : list
        One magicgui widget per non-device parameter, in signature order.
    """
    device_widgets: list[mgw_bases.ValueWidget[Any]] = []
    param_widgets: list[mgw_bases.ValueWidget[Any]] = []

    for p in spec.parameters:
        if p.hidden or p.actions is not None:
            continue
        if p.kind is ParamKind.VAR_KEYWORD:
            continue
        w = cast("mgw_bases.ValueWidget[Any]", create_param_widget(p))
        is_device_param = (
            p.device_proto is not None
            or isdevicesequence(p.annotation)
            or isdeviceset(p.annotation)
            or (p.kind is ParamKind.VAR_POSITIONAL and isdevice(p.annotation))
        )
        if is_device_param:
            device_widgets.append(w)
        else:
            param_widgets.append(w)

    return device_widgets, param_widgets


def _build_devices_group(
    device_widgets: list[mgw_bases.ValueWidget[Any]],
) -> QtW.QGroupBox | None:
    """Build the *Devices* group box.

    Each device parameter gets its own titled sub-group box containing
    its widget (a ``DeviceSequenceEdit`` checkbox list for multi-select,
    or a ``ComboBox`` for single-select).  Returns ``None`` when there are
    no device parameters.
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
        sub_layout.setContentsMargins(4, 4, 4, 4)

        native: QtW.QWidget = w.native
        sub_layout.addWidget(native)
        devices_layout.addWidget(sub_group)

    return devices_group


def _build_params_group(
    param_widgets: list[mgw_bases.ValueWidget[Any]],
) -> QtW.QGroupBox | None:
    """Build the *Parameters* group box using a ``QFormLayout``.

    Each plain parameter (scalar, Literal, …) is added as a labelled
    form row.  Returns ``None`` when there are no plain parameters.
    """
    if not param_widgets:
        return None

    params_group = QtW.QGroupBox("Parameters")
    params_form = QtW.QFormLayout(params_group)
    params_form.setContentsMargins(4, 6, 4, 4)

    for w in param_widgets:
        native: QtW.QWidget = w.native
        label_text: str = getattr(w, "label", w.name)
        params_form.addRow(label_text, native)

    return params_group


def _build_run_buttons(
    spec: PlanSpec,
    parent: QtW.QWidget,
    page_layout: QtW.QVBoxLayout,
    run_callback: Callable[[], None],
    toggle_callback: Callable[[bool], None],
    pause_callback: Callable[[bool], None],
) -> tuple[QtW.QPushButton, QtW.QPushButton | None]:
    """Build run (and optionally pause) buttons and add them to *page_layout*."""
    run_layout = QtW.QHBoxLayout()
    run_container = QtW.QWidget(parent)

    run_button = QtW.QPushButton("Run")
    if spec.togglable:
        run_button.setCheckable(True)
        run_button.toggled.connect(toggle_callback)
    else:
        run_button.clicked.connect(run_callback)
    run_layout.addWidget(run_button)

    pause_button: QtW.QPushButton | None = None
    if spec.togglable and spec.pausable:
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
    """Build the actions group box and add it to *page_layout* if needed."""
    actions_params = [p for p in spec.parameters if p.actions is not None]
    if not actions_params:
        return None, {}

    actions_group = QtW.QGroupBox("Actions")
    actions_layout = QtW.QHBoxLayout(actions_group)
    actions_group.setEnabled(False)

    action_buttons: dict[str, ActionButton] = {}
    for p in actions_params:
        if p.actions is None:
            continue
        action_list: list[Action] = (
            [p.actions] if isinstance(p.actions, Action) else list(p.actions)
        )
        for action in action_list:
            btn = ActionButton(action)
            if action.togglable:
                btn.toggled.connect(
                    lambda checked, name=action.name: action_toggled_callback(
                        checked, name
                    )
                )
            else:
                btn.clicked.connect(
                    lambda _, name=action.name: action_clicked_callback(name)
                )
            action_buttons[action.name] = btn
            actions_layout.addWidget(btn)

    page_layout.addWidget(actions_group)
    return actions_group, action_buttons


def create_plan_widget(
    spec: PlanSpec,
    run_callback: Callable[[], None] | None = None,
    toggle_callback: Callable[[bool], None] | None = None,
    pause_callback: Callable[[bool], None] | None = None,
    action_clicked_callback: Callable[[str], None] | None = None,
    action_toggled_callback: Callable[[bool, str], None] | None = None,
) -> PlanWidget:
    """Build a complete ``PlanWidget`` for *spec*.

    Parameters
    ----------
    spec : PlanSpec
        The plan specification to build a widget for.
    run_callback : Callable[[], None] | None, optional
        Connected to ``run_button.clicked`` for non-togglable plans.
    toggle_callback : Callable[[bool], None] | None, optional
        Connected to ``run_button.toggled`` for togglable plans.
    pause_callback : Callable[[bool], None] | None, optional
        Connected to ``pause_button.toggled`` for pausable plans.
    action_clicked_callback : Callable[[str], None] | None, optional
        Called with ``action_name`` when a non-togglable action fires.
    action_toggled_callback : Callable[[bool, str], None] | None, optional
        Called with ``(checked, action_name)`` when a togglable action fires.

    Returns
    -------
    PlanWidget
        Fully constructed widget, ready to be added to a ``QStackedWidget``.
    """
    page = QtW.QWidget()
    page_layout = QtW.QVBoxLayout(page)
    page_layout.setContentsMargins(4, 4, 4, 4)
    page_layout.setSpacing(4)

    # Build device + parameter widgets and assemble the two group boxes
    device_widgets, param_widgets = _build_param_widgets(spec)

    # Combine into one flat list for the container (preserves .parameters access)
    all_widgets = device_widgets + param_widgets
    container = mgw.Container(widgets=all_widgets)

    devices_group = _build_devices_group(device_widgets)
    params_group = _build_params_group(param_widgets)

    if devices_group is not None:
        page_layout.addWidget(devices_group)
    if params_group is not None:
        page_layout.addWidget(params_group)

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

    return PlanWidget(
        spec=spec,
        group_box=page,
        run_button=run_button,
        pause_button=pause_button,
        container=container,
        actions_group=actions_group,
        action_buttons=action_buttons,
    )


class PlanInfoDialog(QtW.QDialog):
    """Dialog to provide information to the user.

    Parameters
    ----------
    title : str
        The title of the dialog window.
    text : str
        The text to display in the text edit area (rendered as Markdown).
    parent : QtWidgets.QWidget | None, optional
        The parent widget, by default ``None``.
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
        """Create and show the dialog in one step.

        Parameters
        ----------
        title : str
            The title of the dialog window.
        text : str
            The text to display in the text edit area.
        parent : QtWidgets.QWidget | None, optional
            The parent widget, by default ``None``.

        Returns
        -------
        int
            Dialog result code (``QDialog.Accepted`` or ``QDialog.Rejected``).
        """
        dialog = cls(title, text, parent)
        return dialog.exec()
