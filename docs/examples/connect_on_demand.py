"""The session of the guide "How to connect a device on demand"."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003
from typing import Annotated

from ophyd_async.core import NotConnectedError, StandardReadable
from ophyd_async.epics.core import epics_signal_rw
from psygnal import Signal
from qtpy.QtWidgets import QPushButton, QVBoxLayout, QWidget

from redsun import (
    AsDevice,
    AsPresenter,
    AsView,
    Declare,
    DeviceMapping,
    Link,
    Placement,
    SessionConfig,
    slot,
)
from redsun.qt import Dock, QtSession


class MyMotor(StandardReadable):
    def __init__(self, prefix: str, name: str = "") -> None:
        with self.add_children_as_readables():
            self.position = epics_signal_rw(float, f"{prefix}Position")
        super().__init__(name=name)


# --8<-- [start:controller]
class MyController:
    sig_connected = Signal(str)
    sig_not_connected = Signal(str, str)

    def __init__(
        self, name: str, *, devices: DeviceMapping, config: SessionConfig
    ) -> None:
        self.name = name
        self.devices = devices
        self.mock = config.mock

    @slot
    async def connect_motor(self) -> None:
        motor = self.devices["motor"]
        try:
            await motor.connect(mock=self.mock, timeout=5)
        except NotConnectedError as e:
            self.sig_not_connected.emit(motor.name, str(e))
            return
        self.sig_connected.emit(motor.name)


# --8<-- [end:controller]
# --8<-- [start:view]
class MyView(QWidget):
    placement: Placement = Dock("left")
    sig_connect_clicked = Signal()

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self.button = QPushButton("Connect")
        self.button.clicked.connect(lambda: self.sig_connect_clicked.emit())
        QVBoxLayout(self).addWidget(self.button)

    @slot
    def on_connected(self, device: str) -> None:
        self.button.setEnabled(False)

    @slot
    def on_not_connected(self, device: str, reason: str) -> None:
        self.button.setToolTip(reason)


# --8<-- [end:view]
# --8<-- [start:session]
class MyApp(QtSession):
    # --8<-- [start:declare]
    motor: Annotated[AsDevice[MyMotor], Declare(prefix="MOTOR:", autoconnect=False)]
    # --8<-- [end:declare]
    ctrl: AsPresenter[MyController]
    panel: AsView[MyView]

    def wire(self) -> Iterator[Link]:
        yield self.panel.sig_connect_clicked, self.ctrl.connect_motor
        yield self.ctrl.sig_connected, self.panel.on_connected
        yield self.ctrl.sig_not_connected, self.panel.on_not_connected


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
