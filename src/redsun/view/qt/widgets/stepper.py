"""Qt stepper widget module.

Although the motor model is the same accross all types of motorized devices RedSun can accomodate,
the user interface is adapted to the specific needs of each device category for easier code management
and better user experience.

Each stepper motor is categorized in a QGroupBox, and each axis is assigned to a row in the group.
Row positioning is determined by the configuration file, .e.g.:

.. code-block:: yaml

    motors:
        My Motor:
            - axes: ["X", "Y", "Z"]

With this configuration, the axis will be shown in the declared order (so X will be the first row, Y the second, and Z the third).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sunflare.view.qt import BaseWidget
from sunflare.virtualbus import Signal, slot
from sunflare.log import Loggable

from qtpy import QtWidgets
from qtpy.QtGui import QRegularExpressionValidator
from qtpy.QtCore import Qt, QRegularExpression

if TYPE_CHECKING:
    from typing import Any, Tuple

    from redsun.controller.virtualbus import HardwareVirtualBus

    from sunflare.config import MotorModelInfo
    from sunflare.virtualbus import VirtualBus

__all__ = ["StepperMotorWidget"]


class StepperMotorWidget(BaseWidget, Loggable):
    r"""Qt stepper motor widget.

    The widget groups each motor into a QGroupBox, and each axis of the motor has its own row.

    The widget gives users the ability to control the following options for each axis:
    - moving the motor up and down;
    - changing the step size.

    Whenever a change happens in the GUI, the virtual bus is notified, and from there
    the signals is routed to the motor controller.

    Parameters
    ----------
    motors_info: dict[str, MotorModelInfo]
        Dictionary of currently available motor models.
    virtual_bus : HardwareVirtualBus
        The virtual bus instance for the RedSun instance.
    module_bus : VirtualBus
        The inter-module virtual bus instance.
    
    Signals
    -------
    sigStepUp : Signal(str, str)
        `psygnal.Signal` emitted when the user clicks the "+" button. \
        Carries: motor name, axis.
    sigStepDown : Signal(str, str)
        `psygnal.Signal` emitted when the user clicks the "-" button. \
        Carries: motor name, axis.
    sigStepSizeChanged : Signal(str, str, float)
        `psygnal.Signal` emitted when the user changes the step size. \
        Carries: motor name, axis, new step size.
    """

    # redefining the virtual
    # bus only for type
    # hinting purposes
    _virtual_bus: HardwareVirtualBus

    sigStepUp: Signal = Signal(str, str)
    sigStepDown: Signal = Signal(str, str)
    sigStepSizeChanged: Signal = Signal(str, str, float)

    def __init__(
        self,
        motors_info: dict[str, MotorModelInfo],
        virtual_bus: HardwareVirtualBus,
        module_bus: VirtualBus,
    ) -> None:
        super().__init__(virtual_bus, module_bus)
        self._motors_info = motors_info

        self.grid = QtWidgets.QGridLayout()
        self.setLayout(self.grid)
        self.groups: dict[str, QtWidgets.QGroupBox] = {}
        self.labels: dict[str, QtWidgets.QLabel] = {}
        self.buttons: dict[str, QtWidgets.QPushButton] = {}
        self.lineEdits: dict[str, QtWidgets.QLineEdit] = {}

        # Regular expression for a valid floating-point number
        float_regex = QRegularExpression(r"^[-+]?\d*\.?\d+$")
        self.validator = QRegularExpressionValidator(float_regex)

        # iterate over the motor models and create a group
        # widget for each one; axis are grouped in the rows of each group
        for num_motor, (name, info) in enumerate(self._motors_info.items()):
            self.groups[name] = QtWidgets.QGroupBox(name)
            self.groups[name].setAlignment(Qt.AlignmentFlag.AlignHCenter)
            for ax in info.axes:
                # widgets setup
                self.labels["label:{}:{}".format(name, ax)] = QtWidgets.QLabel(
                    f"<strong>{ax}</strong>"
                )
                self.labels["label:{}:{}".format(name, ax)].setTextFormat(
                    Qt.TextFormat.RichText
                )
                self.labels["pos:{}:{}".format(name, ax)] = QtWidgets.QLabel(
                    f"<strong>{0:.2f} µm</strong>"
                )
                self.labels["pos:{}:{}".format(name, ax)].setTextFormat(
                    Qt.TextFormat.RichText
                )
                self.buttons["up:{}:{}".format(name, ax)] = QtWidgets.QPushButton("+")
                self.buttons["down:{}:{}".format(name, ax)] = QtWidgets.QPushButton("-")
                self.lineEdits["step:{}:{}".format(name, ax)] = QtWidgets.QLineEdit(
                    str(info.step_size)
                )
                self.labels["step_egu:{}:{}".format(name, ax)] = QtWidgets.QLabel(
                    str(" {}".format(info.step_egu))
                )

                # signal connection
                self.buttons["up:{}:{}".format(name, ax)].clicked.connect(
                    lambda *_, axis=ax: self.sigStepUp.emit(name, axis)
                )
                self.buttons["down:{}:{}".format(name, ax)].clicked.connect(
                    lambda *_, axis=ax: self.sigStepDown.emit(name, axis)
                )
                self.lineEdits["step:{}:{}".format(name, ax)].textEdited.connect(
                    lambda *_, name=name, axis=ax: self._validate_and_notify(name, axis)
                )

                # grid layout
                self.grid.addWidget(
                    self.labels["label:{}:{}".format(name, ax)], num_motor, 0
                )
                self.grid.addWidget(
                    self.labels["pos:{}:{}".format(name, ax)], num_motor, 1
                )
                self.grid.addWidget(
                    self.buttons["up:{}:{}".format(name, ax)], num_motor, 2
                )
                self.grid.addWidget(
                    self.buttons["down:{}:{}".format(name, ax)], num_motor, 3
                )
                self.grid.addWidget(QtWidgets.QLabel("Step"), num_motor, 4)
                self.grid.addWidget(
                    self.lineEdits["step:{}:{}".format(name, ax)], num_motor, 5
                )
                self.grid.addWidget(
                    self.labels["step_egu:{}:{}".format(name, ax)], num_motor, 6
                )

    @slot(private=True)
    def _validate_and_notify(self, name: str, axis: str) -> None:
        """Validate the new step size value and notify the virtual bus when input is accepted.

        Private slot not exposed to the user.

        Parameters
        ----------
        name : str
            Motor name.
        axis : str
            Motor axis.
        """
        # Validate the input using the validator
        input = self.lineEdits["step:{}:{}".format(name, axis)].text()

        # can't do much for type hinting here since the validator returns
        # a non-annotated tuple of unknown types
        value: Tuple[QRegularExpressionValidator.State, Any, Any] = (
            self.validator.validate(input, 0)
        )
        state = value[0]

        if state == QRegularExpressionValidator.State.Invalid:
            # Set red border if input is invalid
            self.lineEdits["step:{}:{}".format(name, axis)].setStyleSheet(
                "border: 2px solid red;"
            )
        else:
            # Set default border if input is valid
            self.lineEdits["step:{}:{}".format(name, axis)].setStyleSheet("")

        # only emit when input is acceptable, discarding intermediate state
        if state == QRegularExpressionValidator.State.Acceptable:
            self.debug(f"Step size changed: {name}, {axis}, {input}")
            self.sigStepSizeChanged.emit(name, axis, float(input))

    def registration_phase(self) -> None:  # noqa: D102
        # inherited docstring
        # no registration needed; all signals are already
        # built-in in the virtual bus
        ...

    def connection_phase(self) -> None:  # noqa: D102
        self.sigStepUp.connect(self._virtual_bus.sigStepperStepUp)
        self.sigStepDown.connect(self._virtual_bus.sigStepperStepDown)
        self.sigStepSizeChanged.connect(self._virtual_bus.sigStepperStepSizeChanged)
