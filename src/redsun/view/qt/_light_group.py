"""One light's controls in the light view."""

from __future__ import annotations

from typing import TYPE_CHECKING

from psygnal import Signal
from qtpy import QtCore
from qtpy import QtWidgets as QtW

from ._positioner_group import LIMIT

if TYPE_CHECKING:
    from redsun.utils.devices import LightInfo

THROTTLE_MS = 100
"""Least milliseconds between two writes while the slider is dragged."""

DEFAULT_PRECISION = 2
"""Decimals of an intensity whose descriptor gives none."""


class LightGroup(QtW.QGroupBox):
    """A light's on/off button and, when it has one, its intensity.

    The controls show what the light reads back. The intensity is written when
    the slider is let go, when Enter is pressed in the field, and, with
    `write_while_dragging`, during a drag at most every 100 ms.
    """

    sig_enabled = Signal(str, bool)
    """Device, and the state asked for."""

    sig_intensity = Signal(str, float)
    """Device, and the intensity asked for."""

    def __init__(
        self,
        device: str,
        info: LightInfo,
        *,
        write_while_dragging: bool,
        parent: QtW.QWidget | None = None,
    ) -> None:
        super().__init__(device, parent)
        self._device = device
        self._dragging_writes = write_while_dragging
        self._pending: float | None = None
        self._latest: float | None = None
        layout = QtW.QVBoxLayout(self)

        self._toggle = QtW.QPushButton("On", self)
        self._toggle.setObjectName("toggle")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(info.enabled)
        self._toggle.setAccessibleName(f"Switch {device}")
        # the button shows the state read back; a click only asks
        self._toggle.clicked.connect(self._ask_toggle)
        layout.addWidget(self._toggle)
        self._controls: list[QtW.QWidget] = [self._toggle]

        self._slider: QtW.QSlider | None = None
        self._field: QtW.QDoubleSpinBox | None = None
        if info.intensity is not None:
            decimals = DEFAULT_PRECISION if info.precision is None else info.precision
            self._scale = 10**decimals
            row = QtW.QHBoxLayout()
            low, high = info.limits
            if low is not None and high is not None:
                self._slider = QtW.QSlider(QtCore.Qt.Orientation.Horizontal, self)
                self._slider.setObjectName("slider")
                self._slider.setAccessibleName(f"{device} intensity")
                self._slider.setRange(
                    round(low * self._scale), round(high * self._scale)
                )
                self._slider.setValue(round(info.intensity * self._scale))
                self._slider.valueChanged.connect(self._slider_moved)
                self._slider.sliderReleased.connect(self._slider_released)
                row.addWidget(self._slider, 1)
                self._controls.append(self._slider)
            self._field = QtW.QDoubleSpinBox(self)
            self._field.setObjectName("intensity")
            self._field.setAccessibleName(f"{device} intensity value")
            self._field.setLocale(QtCore.QLocale.c())
            self._field.setDecimals(decimals)
            self._field.setRange(
                -LIMIT if low is None else low, LIMIT if high is None else high
            )
            self._field.setKeyboardTracking(False)
            self._field.setValue(info.intensity)
            self._field.editingFinished.connect(self._field_entered)
            row.addWidget(self._field)
            row.addWidget(QtW.QLabel(info.units or "", self))
            layout.addLayout(row)
            self._controls.append(self._field)
            self._timer = QtCore.QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.setInterval(THROTTLE_MS)
            self._timer.timeout.connect(self._write_pending)

        self._state = QtW.QLabel("", self)
        self._state.setObjectName("state")
        self._state.setWordWrap(True)
        layout.addWidget(self._state)

    def set_enabled(self, on: bool) -> None:
        """Show whether the light is on, as read back."""
        self._toggle.setChecked(on)

    def set_intensity(self, value: float) -> None:
        """Show the intensity read back, unless the user is dragging or typing."""
        self._latest = value
        if self._field is None or self._busy():
            return
        self._show(value)

    def set_failed(self, message: str) -> None:
        """Show why the last write failed."""
        self._state.setText(f"failed: {message}")
        self._state.setToolTip(message)

    def set_locked(self, locked: bool) -> None:
        """Disable the controls while *locked*; readbacks keep updating."""
        for widget in self._controls:
            widget.setEnabled(not locked)

    def set_write_while_dragging(self, on: bool) -> None:
        """Write the intensity during a drag as well, at most every 100 ms."""
        self._dragging_writes = on

    def _busy(self) -> bool:
        dragging = self._slider is not None and self._slider.isSliderDown()
        typing = self._field is not None and self._field.hasFocus()
        return dragging or typing

    def _show(self, value: float) -> None:
        if self._field is not None:
            with QtCore.QSignalBlocker(self._field):
                self._field.setValue(value)
        if self._slider is not None:
            with QtCore.QSignalBlocker(self._slider):
                self._slider.setValue(round(value * self._scale))

    def _ask_toggle(self, checked: bool) -> None:
        # undo Qt's own toggle: the readback decides what the button shows
        with QtCore.QSignalBlocker(self._toggle):
            self._toggle.setChecked(not checked)
        self.sig_enabled.emit(self._device, checked)

    def _slider_moved(self, steps: int) -> None:
        assert self._slider is not None and self._field is not None
        value = steps / self._scale
        with QtCore.QSignalBlocker(self._field):
            self._field.setValue(value)
        if not self._slider.isSliderDown():
            self.sig_intensity.emit(self._device, value)
        elif self._dragging_writes:
            self._pending = value
            if not self._timer.isActive():
                self._write_pending()

    def _write_pending(self) -> None:
        if self._pending is not None:
            self.sig_intensity.emit(self._device, self._pending)
            self._pending = None
            self._timer.start()

    def _slider_released(self) -> None:
        assert self._slider is not None
        self._timer.stop()
        self._pending = None
        self.sig_intensity.emit(self._device, self._slider.value() / self._scale)

    def _field_entered(self) -> None:
        assert self._field is not None
        self.sig_intensity.emit(self._device, self._field.value())
        if self._latest is not None and not self._busy():
            self._show(self._latest)
