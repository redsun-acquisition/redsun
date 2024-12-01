"""Qt motor widget module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sunflare.view.qt import BaseWidget
from sunflare.virtualbus import Signal

from qtpy import QtWidgets
from qtpy.QtCore import Qt

if TYPE_CHECKING:
    from redsun.controller.virtualbus import HardwareVirtualBus

    from sunflare.config import MotorModelInfo
    from sunflare.virtualbus import VirtualBus


class StepperMotorWidget(BaseWidget):
    """Qt motor widget class.

    Parameters
    ----------
    motors_info: dict[str, MotorModelInfo]
        Dictionary of currently available motor models.
    virtual_bus : HardwareVirtualBus
        The virtual bus instance for the RedSun instance.
    module_bus : VirtualBus
        The inter-module virtual bus instance.
    """

    # TODO: these need to be documented with
    # the description field in the Signal class;
    # but first the virtual bus needs to be reworked
    sigStepUp: Signal = Signal(str, str)
    sigStepDown: Signal = Signal(str, str)

    def __init__(
        self,
        motors_info: dict[str, MotorModelInfo],
        virtual_bus: HardwareVirtualBus,
        module_bus: VirtualBus,
    ) -> None:
        super().__init__(virtual_bus, module_bus)

        self.grid = QtWidgets.QGridLayout()
        self.setLayout(self.grid)

        for name, info in motors_info.items():
            group = QtWidgets.QGroupBox(name)
            group.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            labels: dict[str, QtWidgets.QLabel] = {}
            buttons: dict[str, QtWidgets.QPushButton] = {}
            lineEdits: dict[str, QtWidgets.QLineEdit] = {}
            for ax in info.axes:
                label = QtWidgets.QLabel(f"<strong>{ax}</strong>")
                label.setTextFormat(Qt.TextFormat.RichText)
                labels["label:" + ax] = label

                label = QtWidgets.QLabel(f"<strong>{0:.2f} µm</strong>")
                label.setTextFormat(Qt.TextFormat.RichText)
                labels["pos:" + ax] = label

                button = QtWidgets.QPushButton("+")
                buttons["up:" + ax] = button

                button = QtWidgets.QPushButton("-")
                buttons["down:" + ax] = button

                lineEdit = QtWidgets.QLineEdit(str(info.step_size))
                lineEdits["step:" + ax] = lineEdit

                label = QtWidgets.QLabel(str(" {}".format(info.step_egu)))
                labels["step_egu:" + ax] = QtWidgets.QLabel(" µm")

                # signal connection
                buttons["up:" + ax].clicked.connect(
                    lambda *_, axis=ax: self.sigStepUp.emit(name, axis)
                )
                buttons["down:" + ax].clicked.connect(
                    lambda *_, axis=ax: self.sigStepDown.emit(name, axis)
                )
