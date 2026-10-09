"""One device's controls in the positioner view."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Literal, get_args

from psygnal import Signal
from qtpy import QtCore, QtGui
from qtpy import QtWidgets as QtW

from ._icons import set_icon

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from redsun.utils.devices import AxisInfo

DEFAULT_PRECISION = 2
"""Decimals shown for an axis whose descriptor gives no precision."""

LIMIT = 1e9
"""Largest step or target magnitude the controls accept."""

StepBox = Literal["combobox", "spinbox"]
"""The control choosing an axis' step size: a list of sizes, or a number box."""


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


def tool_button(icon: str, words: str, parent: QtW.QWidget) -> QtW.QToolButton:
    """Return a compact button showing *icon*, with *words* for its tooltip and screen readers."""
    button = QtW.QToolButton(parent)
    set_icon(button, icon, words)
    return button


class AxisRow(QtW.QWidget):
    """An axis: name, readback and units, then steps and a go-to field.

    A frame shows that the row or one of its step buttons has focus.
    """

    sig_step = Signal(float)
    """Signed step, when a step button is pressed or repeats, or `step_by` runs."""

    sig_go = Signal(float)
    """Target, when a target in range is sent."""

    sig_refused = Signal(str)
    """Why a target was not sent."""

    def __init__(
        self,
        axis: str,
        info: AxisInfo,
        steps: Sequence[float],
        repeat_delay: int,
        repeat_interval: int,
        step_box: StepBox,
        parent: QtW.QWidget,
    ) -> None:
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"{axis} axis")
        self.axis = axis
        self.decimals = (
            DEFAULT_PRECISION
            if info.readback.precision is None
            else info.readback.precision
        )
        self.position = info.readback.value
        self.step = 1.0 if 1.0 in steps else steps[0]

        self.readback = QtW.QLabel(self.format_value(info.readback.value), self)
        self.readback.setObjectName(f"readback:{axis}")
        self.readback.setAccessibleName(f"{axis} position")
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
        font.setPointSizeF(self.font().pointSizeF())
        self.readback.setFont(font)
        self.readback.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.readback.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.buttons: list[QtW.QToolButton] = []
        for sign, label in ((-1.0, "minus"), (1.0, "plus")):
            direction = "down" if sign < 0 else "up"
            button = tool_button(label, f"Step {axis} {direction}", self)
            button.setObjectName(f"{label}:{axis}")
            button.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
            button.setFixedWidth(button.sizeHint().height())
            button.installEventFilter(self)
            button.setAutoRepeat(True)
            button.setAutoRepeatDelay(repeat_delay)
            button.setAutoRepeatInterval(repeat_interval)
            # a held button emits pressed at each repeat and nothing on
            # release, where clicked would add one step more
            button.pressed.connect(
                lambda s=sign: self.sig_step.emit(s * self.step_size())
            )
            self.buttons.append(button)

        centre = QtCore.Qt.AlignmentFlag.AlignCenter
        self.box: QtW.QComboBox | QtW.QDoubleSpinBox
        if step_box == "spinbox":
            self.box = QtW.QDoubleSpinBox(self)
            self.box.setLocale(QtCore.QLocale.c())
            decimals = max(
                0,
                *(
                    -int(Decimal(repr(step)).normalize().as_tuple().exponent)
                    for step in steps
                ),
            )
            self.box.setDecimals(decimals)
            self.box.setRange(min(steps), max(steps))
            self.box.setStepType(QtW.QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
            self.box.setValue(self.step)
            self.box.setAlignment(centre)
            # its hint makes room for the widest size in range beside its arrows
            self.box.setFixedWidth(self.box.sizeHint().width())
        else:
            self.box = QtW.QComboBox(self)
            self.box.setEditable(True)
            self.box.setInsertPolicy(QtW.QComboBox.InsertPolicy.NoInsert)
            self.box.addItems([f"{step:g}" for step in steps])
            for index in range(self.box.count()):
                self.box.setItemData(
                    index, centre, QtCore.Qt.ItemDataRole.TextAlignmentRole
                )
            self.box.setCurrentIndex(self.box.findText(f"{self.step:g}"))
            self.box.setValidator(number_validator(0.0, LIMIT, self.box))
            if (edit := self.box.lineEdit()) is not None:
                edit.setAlignment(centre)
            # the box would otherwise claim room for its arrow and frame at
            # their widest, more than a narrow dock has; a fixed width, unlike
            # an ignored size policy, still reserves its column in the grid
            self.box.setFixedWidth(self.fontMetrics().horizontalAdvance("0.001") + 32)
        self.box.setObjectName(f"step:{axis}")
        self.box.setAccessibleName(f"{axis} step size")
        self.box.setToolTip("Step size")

        self.target = QtW.QLineEdit(self.format_value(info.readback.value), self)
        self.target.setObjectName(f"goto:{axis}")
        self.target.setAccessibleName(f"{axis} target")
        self.target.setMinimumWidth(self.fontMetrics().horizontalAdvance("0" * 6))
        self.validator = number_validator(-LIMIT, LIMIT, self.target)
        self.target.setValidator(self.validator)
        self.set_limits(*info.readback.limits)
        self.target.returnPressed.connect(self.go)
        self.go_button = tool_button("crosshairs-gps", f"Go {axis} to target", self)
        self.go_button.setFixedWidth(self.go_button.sizeHint().height())
        self.go_button.setObjectName(f"go:{axis}")
        self.go_button.clicked.connect(self.go)
        self.controls: tuple[QtW.QWidget, ...] = (
            *self.buttons,
            self.box,
            self.target,
            self.go_button,
        )

        grid = QtW.QGridLayout(self)
        grid.setContentsMargins(4, 2, 4, 2)
        grid.addWidget(QtW.QLabel(axis, self), 0, 0, 1, 3)
        grid.addWidget(self.readback, 0, 3, 1, 2)
        grid.addWidget(QtW.QLabel(info.readback.units or "", self), 0, 5)
        grid.addWidget(self.buttons[0], 1, 0)
        grid.addWidget(self.box, 1, 1)
        grid.addWidget(self.buttons[1], 1, 2)
        grid.addWidget(self.target, 1, 3, 1, 2)
        grid.addWidget(self.go_button, 1, 5)
        grid.setColumnStretch(3, 1)

    def format_value(self, value: float) -> str:
        """Return *value* with this axis' decimals."""
        return f"{value:.{self.decimals}f}"

    def set_limits(self, low: float | None, high: float | None) -> None:
        """Take targets from *low* to *high* only; `None` for no bound."""
        self.low, self.high = low, high
        self.validator.setBottom(-LIMIT if low is None else low)
        self.validator.setTop(LIMIT if high is None else high)
        self.target.setToolTip(f"Target, {self.range_text()}")

    def range_text(self) -> str:
        """Return the targets this axis takes, in words."""
        if self.low is None and self.high is None:
            return "any number"
        low = "any" if self.low is None else self.format_value(self.low)
        high = "any" if self.high is None else self.format_value(self.high)
        return f"from {low} to {high}"

    def step_size(self) -> float:
        """Return the step in the box, or the last valid one if it holds none."""
        if isinstance(self.box, QtW.QDoubleSpinBox):
            return self.box.value()
        try:
            step = float(self.box.currentText())
        except ValueError:
            return self.step
        if step > 0:
            self.step = step
        return self.step

    def go(self) -> None:
        """Send the typed target if it is a number in range, or say why not."""
        if not self.target.hasAcceptableInput():
            text = self.target.text() or "an empty target"
            self.sig_refused.emit(f"{self.axis}: {text} is not {self.range_text()}")
            return
        self.target.setModified(False)
        self.sig_go.emit(float(self.target.text()))

    def show_position(self, value: float) -> None:
        """Show *value* as the readback, and as the target unless one is typed."""
        self.position = value
        self.readback.setText(self.format_value(value))
        if not self.target.hasFocus() and not self.target.isModified():
            self.target.setText(self.format_value(value))

    def holds_focus(self) -> bool:
        """Tell whether the row or one of its step buttons has focus."""
        return self.hasFocus() or any(button.hasFocus() for button in self.buttons)

    def step_by(self, sign: float) -> None:
        """Step by the chosen size times *sign*, unless the row is locked."""
        if self.buttons[0].isEnabled():
            self.sig_step.emit(sign * self.step_size())

    def eventFilter(
        self, watched: QtCore.QObject | None, event: QtCore.QEvent | None
    ) -> bool:
        """Repaint when a step button gains or loses focus."""
        if event is not None and event.type() in (
            QtCore.QEvent.Type.FocusIn,
            QtCore.QEvent.Type.FocusOut,
        ):
            self.update()
        return False

    def paintEvent(self, event: QtGui.QPaintEvent | None) -> None:
        """Frame the row while it or one of its step buttons has focus."""
        if event is not None:
            super().paintEvent(event)
        if self.holds_focus():
            painter = QtW.QStylePainter(self)
            option = QtW.QStyleOptionFocusRect()
            option.initFrom(self)
            painter.drawPrimitive(QtW.QStyle.PrimitiveElement.PE_FrameFocusRect, option)

    def focusInEvent(self, event: QtGui.QFocusEvent | None) -> None:
        """Repaint to show the focus frame."""
        if event is not None:
            super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event: QtGui.QFocusEvent | None) -> None:
        """Repaint to clear the focus frame."""
        if event is not None:
            super().focusOutEvent(event)
        self.update()


class PositionerGroup(QtW.QGroupBox):
    """A device's axes, its state, and buttons to stop it and save where it is.

    Parameters
    ----------
    steps
        Step sizes offered in each axis' step box; a typed size is accepted.
    repeat_delay
        Milliseconds a step button is held before its step repeats.
    repeat_interval
        Milliseconds between two repeated steps.
    step_box
        `"combobox"` lists the sizes in *steps*; `"spinbox"` takes any size
        from the smallest to the largest of them, starting from the default
        one, and its arrows move it by decades.

    Raises
    ------
    ValueError
        If *steps* is empty, or *step_box* is neither choice.
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
        step_box: StepBox = "combobox",
        parent: QtW.QWidget | None = None,
    ) -> None:
        if not steps:
            raise ValueError("steps holds no step size")
        if step_box not in get_args(StepBox):
            raise ValueError(f"step_box {step_box!r} is not one of {get_args(StepBox)}")
        super().__init__(device, parent)
        layout = QtW.QVBoxLayout(self)
        header = QtW.QHBoxLayout()
        self._controls: list[QtW.QWidget] = []
        self._stop: QtW.QToolButton | None = None
        if any(info.stoppable for info in axes.values()):
            self._stop = tool_button("stop", f"Stop {device}", self)
            self._stop.setObjectName("stop")
            self._stop.clicked.connect(lambda: self.sig_stop.emit(device))
            header.addWidget(self._stop)
            self._controls.append(self._stop)
        header.addStretch(1)
        self._save = tool_button("content-save", f"Save where {device} stands", self)
        self._save.setObjectName("save")
        self._save.clicked.connect(lambda: self.sig_save.emit(device))
        header.addWidget(self._save)
        self._controls.append(self._save)
        layout.addLayout(header)
        self._state = QtW.QLabel("", self)
        self._state.setObjectName("state")
        self._state.setWordWrap(True)
        self._state.setAccessibleName(f"{device} state")
        layout.addWidget(self._state)

        self._step_buttons: list[QtW.QToolButton] = []
        self._rows: dict[str, AxisRow] = {}
        for axis, info in axes.items():
            row = AxisRow(
                axis, info, steps, repeat_delay, repeat_interval, step_box, self
            )
            row.sig_step.connect(
                lambda delta, a=axis: self.sig_move.emit(device, a, delta)
            )
            row.sig_go.connect(
                lambda value, a=axis: self.sig_move_to.emit(device, {a: value})
            )
            row.sig_refused.connect(self.show_message)
            self._rows[axis] = row
            self._controls.extend(row.controls)
            self._step_buttons.extend(row.buttons)
            layout.addWidget(row)

    @property
    def positions(self) -> dict[str, float]:
        """The last readback of each axis."""
        return {axis: row.position for axis, row in self._rows.items()}

    def focused_axis(self) -> str | None:
        """Return the axis whose row or step button has focus, or `None`."""
        return next(
            (axis for axis, row in self._rows.items() if row.holds_focus()), None
        )

    def step(self, axis: str, sign: float) -> None:
        """Step *axis* by its chosen size times *sign*, unless the device is locked."""
        self._rows[axis].step_by(sign)

    def set_readback(self, axis: str, value: float) -> None:
        """Show *value* as the readback of *axis*."""
        self._rows[axis].show_position(value)

    def set_limits(self, axis: str, low: float | None, high: float | None) -> None:
        """Take targets for *axis* from *low* to *high* only; `None` for no bound."""
        self._rows[axis].set_limits(low, high)

    def set_moving(self, moving: bool) -> None:
        """Show that the device moves; a failure stays shown until the next move."""
        if moving:
            self._state.setText("moving")
            self._state.setToolTip("")
        elif self._state.text() == "moving":
            self._state.setText("")

    def show_message(self, message: str) -> None:
        """Show *message* in the state line until the next move."""
        self._state.setText(message)
        self._state.setToolTip(message)

    def set_failed(self, message: str) -> None:
        """Show that the last move failed, and why."""
        self._state.setText(f"failed: {message}")
        self._state.setToolTip(message)

    def set_locked(self, locked: bool) -> None:
        """Disable the controls while *locked*; readbacks keep updating.

        A control holding the focus gives it to its row, or to the first row
        for a button above the rows, so the focus stays with the locked device.
        """
        focus = QtW.QApplication.focusWidget()
        if locked and focus in self._controls:
            # Qt moves the focus off a disabled control to the next one, which
            # can be another device's row, where a held arrow key steps it
            rows = list(self._rows.values())
            row = next(
                (r for r in rows if focus in r.controls), rows[0] if rows else self
            )
            row.setFocus()
        for widget in self._controls:
            widget.setEnabled(not locked)

    def set_repeat_interval(self, milliseconds: int) -> None:
        """Repeat every step button at *milliseconds* while held."""
        for button in self._step_buttons:
            button.setAutoRepeatInterval(milliseconds)
