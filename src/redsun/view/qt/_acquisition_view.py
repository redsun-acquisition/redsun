"""The built-in view running the plans of a session."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from psygnal import Signal
from qtpy import QtCore, QtGui
from qtpy import QtWidgets as QtW

from redsun.engine.actions import ActionState
from redsun.log import Loggable
from redsun.ports import slot
from redsun.presenter import DescribesPlans  # noqa: TC001
from redsun.qt import Dock
from redsun.view import shortcut
from redsun.view.qt.utils import PlanInfoDialog, PlanWidget, create_plan_widget

from ..._settings import Settings  # noqa: TC001

if TYPE_CHECKING:
    from redsun.engine import ProgressState
    from redsun.view import Placement
    from redsun.view.qt.utils import ActionButton


class AcquisitionView(QtW.QWidget, Loggable):
    """Choose a plan, fill its parameters, and run, pause and stop it.

    One `PlanWidget` per plan the presenter describes, chosen from a list,
    and the directory runs write under. The view shows a plan running only
    once the presenter reports it started, and shows why a plan failed until
    it runs again. The plan chosen last is kept in the session's settings.
    `Ctrl+R` runs the chosen plan and `Ctrl+.` stops the running one,
    anywhere in the window.
    """

    placement: Placement = Dock("left")
    """Where the view sits in the main window."""

    sig_launch = Signal(str, dict, tuple)
    """Plan, its parameter values, and the names of the callbacks attached."""

    sig_pause = Signal()
    """The user paused the running plan."""

    sig_resume = Signal()
    """The user resumed the paused plan."""

    sig_stop = Signal()
    """The user stopped the plan."""

    sig_action = Signal(str, bool)
    """Action, and whether its button is pressed."""

    sig_base_dir = Signal(object)
    """The directory the user chose for runs to write under."""

    def __init__(self, name: str, parent: QtW.QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self.plan_widgets: dict[str, PlanWidget] = {}
        self._failures: dict[str, QtW.QLabel] = {}
        self._running: str | None = None
        self._settings: Settings | None = None

        layout = QtW.QVBoxLayout(self)
        top = QtW.QHBoxLayout()
        self._chooser = QtW.QComboBox(self)
        self._chooser.setObjectName("plans")
        self._chooser.setToolTip("Select a plan to run")
        self._info = QtW.QPushButton(self)
        style = self.style()
        assert style is not None
        self._info.setIcon(
            style.standardIcon(QtW.QStyle.StandardPixmap.SP_FileDialogInfoView)
        )
        self._info.setToolTip("Information about the selected plan")
        self._info.setFlat(True)
        self._info.clicked.connect(self._show_info)
        top.addWidget(self._chooser, 1)
        top.addWidget(self._info)
        layout.addLayout(top)

        self._base_dir = QtW.QLineEdit(self)
        self._base_dir.setObjectName("base-dir")
        self._base_dir.setReadOnly(True)
        self._base_dir.setToolTip("Directory runs write under")
        self._choose_root = QtW.QPushButton("Choose root...", self)
        self._choose_root.setObjectName("choose-root")
        self._choose_root.clicked.connect(self._choose_base_dir)
        browse = QtW.QPushButton("Browse root", self)
        browse.setObjectName("browse-root")
        browse.clicked.connect(self._browse_base_dir)
        buttons = QtW.QHBoxLayout()
        buttons.addWidget(self._choose_root)
        buttons.addWidget(browse)
        layout.addWidget(self._base_dir)
        layout.addLayout(buttons)

        self._stack = QtW.QStackedWidget(self)
        layout.addWidget(self._stack)
        self._chooser.currentIndexChanged.connect(self._stack.setCurrentIndex)
        self._chooser.currentTextChanged.connect(self._remember)

    def setup(self, acquisition: DescribesPlans, settings: Settings) -> None:
        """Build one widget per plan *acquisition* describes, and read *settings*."""
        for plan in sorted(acquisition.plans):
            widget = create_plan_widget(
                acquisition.plans[plan],
                run_callback=self._run_clicked,
                toggle_callback=self._run_toggled,
                pause_callback=self._pause_toggled,
                action_clicked_callback=lambda action: self.sig_action.emit(
                    action, True
                ),
                action_toggled_callback=lambda on, action: self.sig_action.emit(
                    action, on
                ),
                plan_callbacks=acquisition.plan_callbacks.get(plan, ()),
                available_callbacks=acquisition.callbacks,
                attached_callbacks=None,
            )
            failure = QtW.QLabel(widget.group_box)
            failure.setObjectName(f"failure:{plan}")
            failure.setWordWrap(True)
            failure.hide()
            box_layout = widget.group_box.layout()
            if box_layout is not None:
                box_layout.addWidget(failure)
            self._failures[plan] = failure
            self.plan_widgets[plan] = widget
            self._stack.addWidget(widget.group_box)
            self._chooser.addItem(plan)
        if not self.plan_widgets:
            empty = QtW.QLabel("No plans are offered.", self)
            empty.setObjectName("no-plans")
            self._stack.addWidget(empty)
        if acquisition.base_dir is not None:
            self.update_base_dir(acquisition.base_dir)
        self._settings = settings
        stored = settings.get(self._key("plan"))
        if isinstance(stored, str) and stored in self.plan_widgets:
            self._chooser.setCurrentText(stored)

    @slot(signal="sig_plan_started")
    def set_started(self, plan: str) -> None:
        """Show *plan* running, and lock the chooser and the root until it ends."""
        widget = self.plan_widgets.get(plan)
        if widget is None:
            self.logger.debug(f"Ignoring the start of an unknown plan {plan!r}")
            return
        self._running = plan
        self._failures[plan].hide()
        self._chooser.setEnabled(False)
        self._choose_root.setEnabled(False)
        widget.toggle(True)

    @slot(signal="sig_plan_done")
    def set_done(self, plan: str) -> None:
        """Show *plan* ended, and free the chooser and the root."""
        self._end(plan)

    @slot(signal="sig_plan_failed")
    def set_failed(self, plan: str, message: str) -> None:
        """Show *plan* ended because of *message*, until it runs again."""
        if self._end(plan):
            self._failures[plan].setText(f"failed: {message}")
            self._failures[plan].show()

    @slot(signal="sig_progress")
    def update_progress(self, scopes: tuple[ProgressState, ...]) -> None:
        """Show the progress of the running plan."""
        if self._running is None:
            self.logger.debug("Ignoring progress with no plan running")
            return
        self.plan_widgets[self._running].show_progress(scopes)

    @slot(signal="sig_action_changed")
    def update_action(self, action: str, state: object) -> None:
        """Set the running plan's button for *action* to *state*."""
        widget = self.plan_widgets.get(self._running or "")
        button = widget.get_action_button(action) if widget is not None else None
        if button is None:
            self.logger.debug(f"Ignoring action {action!r}: no running plan shows it")
            return
        self._set_action_button(button, state)

    @slot(signal="sig_base_dir_changed")
    def update_base_dir(self, path: Path) -> None:
        """Show the directory runs write under."""
        self._base_dir.setText(str(path))

    @shortcut("Ctrl+R", title="Run the chosen plan")
    def run_plan(self) -> None:
        """Run the chosen plan as its Run button does, unless a plan runs."""
        widget = self.plan_widgets.get(self._chooser.currentText())
        if self._running is None and widget is not None:
            # a disabled button, for parameters with problems, ignores the click
            widget.run_button.click()

    @shortcut("Ctrl+.", title="Stop the running plan")
    def stop_plan(self) -> None:
        """Ask to stop the running plan, or the one launched and not yet started."""
        # the view hears of a start after the presenter, which keeps a stop
        # for a launched plan and ignores one with nothing launched
        self.sig_stop.emit()

    def _end(self, plan: str) -> bool:
        widget = self.plan_widgets.get(plan)
        if widget is None:
            self.logger.debug(f"Ignoring the end of an unknown plan {plan!r}")
            return False
        self._running = None
        self._chooser.setEnabled(True)
        self._choose_root.setEnabled(True)
        widget.toggle(False)
        widget.setEnabled(True)
        return True

    def _key(self, setting: str) -> str:
        return f"{self.name}.{setting}"

    def _remember(self, plan: str) -> None:
        if self._settings is not None and plan:
            self._settings.set(self._key("plan"), plan)

    def _run_clicked(self) -> None:
        # a plan that is not continuous has a plain button: Run, then Stop
        if self._running is not None:
            self.sig_stop.emit()
            return
        plan = self._chooser.currentText()
        widget = self.plan_widgets[plan]
        self.sig_launch.emit(plan, widget.parameters, tuple(widget.attached_callbacks))

    def _run_toggled(self, toggled: bool) -> None:
        plan = self._running or self._chooser.currentText()
        widget = self.plan_widgets[plan]
        if toggled:
            # the presenter reports the start; until then the button shows Run
            widget.toggle(False)
            self.sig_launch.emit(
                plan, widget.parameters, tuple(widget.attached_callbacks)
            )
        else:
            self.sig_stop.emit()

    def _pause_toggled(self, paused: bool) -> None:
        if self._running is None:
            return
        self.plan_widgets[self._running].pause(paused)
        (self.sig_pause if paused else self.sig_resume).emit()

    def _set_action_button(self, button: ActionButton, state: object) -> None:
        match state:
            case ActionState.IDLE:
                button.setEnabled(False)
                button.release()
            case ActionState.OFFERED:
                button.setEnabled(True)
            case ActionState.RUNNING:
                button.setEnabled(button.isCheckable())

    def _choose_base_dir(self) -> None:
        chosen = QtW.QFileDialog.getExistingDirectory(
            self, "Directory for acquired data", self._base_dir.text()
        )
        if chosen:
            self.sig_base_dir.emit(Path(chosen))

    def _browse_base_dir(self) -> None:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self._base_dir.text()))

    def _show_info(self) -> None:
        widget = self.plan_widgets.get(self._chooser.currentText())
        if widget is not None:
            PlanInfoDialog.show_dialog(
                "Plan information", widget.spec.docs, parent=self
            )
