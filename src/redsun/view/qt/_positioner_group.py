"""One device's controls in the positioner view."""

from __future__ import annotations

from typing import TYPE_CHECKING

from psygnal import Signal
from qtpy import QtCore, QtGui
from qtpy import QtWidgets as QtW

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from redsun.presenter import AxisInfo

DEFAULT_PRECISION = 2
"""Decimals shown for an axis whose descriptor gives no precision."""

LIMIT = 1e9
"""Largest step or target magnitude the controls accept."""


def number_validator(
    low: float, high: float, parent: QtCore.QObject
) -> QtGui.QDoubleValidator:
    """Return a validator for numbers from *low* to *high*, written with a dot.

    Readbacks are shown with a dot whatever the system locale, so typed
    numbers are read the same way; a group separator is refused.
    """
    locale = QtCore.QLocale.c()
    locale.setNumberOptions(QtCore.QLocale.NumberOption.RejectGroupSeparator)
    validator = QtGui.QDoubleValidator(low, high, 9, parent)
    validator.setLocale(locale)
    return validator


class AxisRow(QtW.QWidget):
    """An axis: name, readback, step buttons and step box, then go-to."""

    sig_step = Signal(float)
    sig_go = Signal(float)

    def __init__(
        self,
        axis: str,
        info: AxisInfo,
        steps: Sequence[float],
        repeat_delay: int,
        repeat_interval: int,
        parent: QtW.QWidget,
    ) -> None:
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.decimals = DEFAULT_PRECISION if info.precision is None else info.precision
        self.position = info.position
        self.low, self.high = info.limits
        self.step = 1.0 if 1.0 in steps else steps[0]

        self.readback = QtW.QLabel(self.format(info.position), self)
        self.readback.setObjectName(f"readback:{axis}")
        self.readback.setFont(
            QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
        )
        self.readback.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.box = QtW.QComboBox(self)
        self.box.setObjectName(f"step:{axis}")
        self.box.setEditable(True)
        self.box.addItems([f"{step:g}" for step in steps])
        self.box.setCurrentText(f"{self.step:g}")
        self.box.setValidator(number_validator(0.0, LIMIT, self.box))
        self.box.setToolTip("Step size")

        self.buttons = []
        for sign, label in ((-1.0, "minus"), (1.0, "plus")):
            button = QtW.QPushButton("-" if sign < 0 else "+", self)
            button.setObjectName(f"{label}:{axis}")
            button.setAutoRepeat(True)
            button.setAutoRepeatDelay(repeat_delay)
            button.setAutoRepeatInterval(repeat_interval)
            # a held button emits pressed at each repeat and nothing on
            # release, where clicked would add one step more
            button.pressed.connect(
                lambda s=sign: self.sig_step.emit(s * self.step_size())
            )
            self.buttons.append(button)

        self.target = QtW.QLineEdit(self.format(info.position), self)
        self.target.setObjectName(f"goto:{axis}")
        self.target.setValidator(
            number_validator(
                -LIMIT if self.low is None else self.low,
                LIMIT if self.high is None else self.high,
                self.target,
            )
        )
        if self.low is not None or self.high is not None:
            low = "" if self.low is None else self.format(self.low)
            high = "" if self.high is None else self.format(self.high)
            self.target.setToolTip(f"Target, from {low} to {high}")
        self.target.returnPressed.connect(self.go)
        self.go_button = QtW.QPushButton("Go", self)
        self.go_button.setObjectName(f"go:{axis}")
        self.go_button.clicked.connect(self.go)

        grid = QtW.QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(QtW.QLabel(axis, self), 0, 0)
        grid.addWidget(self.readback, 0, 1)
        grid.addWidget(QtW.QLabel(info.units or "", self), 0, 2)
        grid.addWidget(self.buttons[0], 0, 3)
        grid.addWidget(self.box, 0, 4)
        grid.addWidget(self.buttons[1], 0, 5)
        grid.addWidget(QtW.QLabel("go to", self), 1, 0)
        grid.addWidget(self.target, 1, 1, 1, 3)
        grid.addWidget(self.go_button, 1, 4)
        grid.setColumnStretch(1, 1)

    def format(self, value: float) -> str:
        """Return *value* with this axis' decimals."""
        return f"{value:.{self.decimals}f}"

    def step_size(self) -> float:
        """Return the step in the box, or the last valid one if it holds none."""
        try:
            step = float(self.box.currentText())
        except ValueError:
            return self.step
        if step > 0:
            self.step = step
        return self.step

    def go(self) -> None:
        """Emit the target typed in the go-to field, if it is a number in range."""
        try:
            target = float(self.target.text())
        except ValueError:
            return
        if (self.low is not None and target < self.low) or (
            self.high is not None and target > self.high
        ):
            return
        self.sig_go.emit(target)

    def show_position(self, value: float) -> None:
        """Show *value* as the readback."""
        self.position = value
        self.readback.setText(self.format(value))

    def set_enabled_controls(self, enabled: bool) -> None:
        """Enable or disable everything but the readback."""
        for widget in (*self.buttons, self.box, self.target, self.go_button):
            widget.setEnabled(enabled)

    def keyPressEvent(self, event: QtGui.QKeyEvent | None) -> None:
        """Step with Left and Right while the row has focus and is not locked."""
        if event is not None and not self.buttons[0].isEnabled():
            super().keyPressEvent(event)
        elif event is not None and event.key() == QtCore.Qt.Key.Key_Left:
            self.sig_step.emit(-self.step_size())
        elif event is not None and event.key() == QtCore.Qt.Key.Key_Right:
            self.sig_step.emit(self.step_size())
        elif event is not None:
            super().keyPressEvent(event)


class PositionerGroup(QtW.QGroupBox):
    """A device's axes, its state, and a button saving where it stands.

    Parameters
    ----------
    steps
        Step sizes offered in each axis' step box; a typed size is accepted.
    repeat_delay
        Milliseconds a step button is held before its step repeats.
    repeat_interval
        Milliseconds between two repeated steps.
    """

    sig_move = Signal(str, str, float)
    """Device, axis and step, when a step is asked."""

    sig_move_to = Signal(str, dict)
    """Device and the positions to go to, by axis."""

    sig_save = Signal(str)
    """Device, when its position is to be saved."""

    sig_stop = Signal(str)
    """Device, when it is to stop."""

    def __init__(
        self,
        device: str,
        axes: Mapping[str, AxisInfo],
        *,
        steps: Sequence[float],
        repeat_delay: int,
        repeat_interval: int,
        parent: QtW.QWidget | None = None,
    ) -> None:
        super().__init__(device, parent)
        self._device = device
        self._state = QtW.QLabel("", self)
        self._state.setObjectName("state")
        self._save = QtW.QPushButton("Save", self)
        self._save.setObjectName("save")
        self._save.setToolTip("Save where this device stands")
        self._save.clicked.connect(lambda: self.sig_save.emit(device))

        self._stop: QtW.QPushButton | None = None
        header = QtW.QHBoxLayout()
        header.addStretch(1)
        header.addWidget(self._state)
        if any(info.stoppable for info in axes.values()):
            self._stop = QtW.QPushButton("Stop", self)
            self._stop.setObjectName("stop")
            self._stop.clicked.connect(lambda: self.sig_stop.emit(device))
            header.addWidget(self._stop)
        header.addWidget(self._save)
        layout = QtW.QVBoxLayout(self)
        layout.addLayout(header)

        self._rows: dict[str, AxisRow] = {}
        for axis, info in axes.items():
            row = AxisRow(axis, info, steps, repeat_delay, repeat_interval, self)
            row.sig_step.connect(
                lambda delta, a=axis: self.sig_move.emit(device, a, delta)
            )
            row.sig_go.connect(
                lambda value, a=axis: self.sig_move_to.emit(device, {a: value})
            )
            self._rows[axis] = row
            layout.addWidget(row)

    def set_readback(self, axis: str, value: float) -> None:
        """Show *value* as the readback of *axis*."""
        self._rows[axis].show_position(value)

    def positions(self) -> dict[str, float]:
        """Return the last readback of each axis."""
        return {axis: row.position for axis, row in self._rows.items()}

    def set_moving(self, moving: bool) -> None:
        """Show that the device moves; a failure stays shown until the next move."""
        if moving:
            self._state.setText("moving")
            self._state.setToolTip("")
        elif self._state.text() == "moving":
            self._state.setText("")

    def set_failed(self, message: str) -> None:
        """Show that the last move failed, with *message* as tooltip."""
        self._state.setText("failed")
        self._state.setToolTip(message)

    def set_locked(self, locked: bool) -> None:
        """Disable the controls while *locked*; readbacks keep updating."""
        for row in self._rows.values():
            row.set_enabled_controls(not locked)
        self._save.setEnabled(not locked)
        if self._stop is not None:
            self._stop.setEnabled(not locked)

    def set_repeat_interval(self, milliseconds: int) -> None:
        """Repeat every step button at *milliseconds* while held."""
        for row in self._rows.values():
            for button in row.buttons:
                button.setAutoRepeatInterval(milliseconds)
