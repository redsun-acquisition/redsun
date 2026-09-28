# /// script
# requires-python = ">=3.11"
# dependencies = ["redsun[pyqt]>=0.14"]
# ///
"""The session built in the "Running a plan from a form" tutorial."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003
from typing import Any, Protocol

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator  # noqa: TC002
from ophyd_async.core import SignalRW, StandardReadable, soft_signal_rw
from psygnal import Signal
from qtpy.QtWidgets import QVBoxLayout, QWidget

from redsun import (
    AsDevice,
    AsPresenter,
    AsView,
    DeviceMapping,
    DevicesOf,
    Link,
    Placement,
    provides,
    slot,
)
from redsun.engine import RunEngine
from redsun.presenter.plan_spec import (
    PlanSpec,
    collect_arguments,
    create_plan_spec,
    resolve_arguments,
)
from redsun.qt import Dock, QtSession
from redsun.view.qt.utils import create_plan_widget


class MyStage(StandardReadable):
    def __init__(self, name: str = "", *, units: str = "mm") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, units=units)
        super().__init__(name=name)


class HasPosition(Protocol):
    position: SignalRW[float]


# --8<-- [start:presenter]
class ScanPresenter:
    sig_finished = Signal()

    def __init__(
        self, name: str, *, stages: DevicesOf[HasPosition], devices: DeviceMapping
    ) -> None:
        self.name = name
        self.stage = stages["stage"]
        self.devices = devices
        self.engine = RunEngine()
        self._spec = create_plan_spec(self.walk, devices)

    # --8<-- [start:plan]
    def walk(self, steps: int = 5, size: float = 1.0) -> MsgGenerator[None]:
        for _ in range(steps):
            position = yield from bps.rd(self.stage.position)
            yield from bps.mv(self.stage.position, position + size)

    # --8<-- [end:plan]
    # --8<-- [start:spec]
    @provides
    def spec(self) -> PlanSpec:
        return self._spec

    # --8<-- [end:spec]
    # --8<-- [start:run]
    @slot
    def run(self, values: dict[str, Any]) -> None:
        resolved = resolve_arguments(self._spec, values, self.devices)
        args, kwargs = collect_arguments(self._spec, resolved)
        future = self.engine(self.walk(*args, **kwargs))
        future.add_done_callback(lambda _: self.sig_finished.emit())

    # --8<-- [end:run]


# --8<-- [end:presenter]
# --8<-- [start:view]
class ScanView(QWidget):
    placement: Placement = Dock("left")
    sig_run = Signal(dict)

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name

    def setup(self, spec: PlanSpec) -> None:
        self.widget = create_plan_widget(spec, run_callback=self.ask_to_run)
        QVBoxLayout(self).addWidget(self.widget.group_box)

    def ask_to_run(self) -> None:
        self.widget.setEnabled(False)
        self.sig_run.emit(self.widget.parameters)

    @slot
    def on_finished(self) -> None:
        self.widget.setEnabled(True)


# --8<-- [end:view]
# --8<-- [start:session]
class ScanSession(QtSession):
    stage: AsDevice[MyStage]
    scan_ctrl: AsPresenter[ScanPresenter]
    scan_view: AsView[ScanView]

    def wire(self) -> Iterator[Link]:
        yield self.scan_view.sig_run, self.scan_ctrl.run
        yield self.scan_ctrl.sig_finished, self.scan_view.on_finished


if __name__ == "__main__":
    ScanSession().run()
# --8<-- [end:session]
