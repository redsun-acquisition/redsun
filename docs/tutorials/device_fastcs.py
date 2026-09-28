# /// script
# requires-python = ">=3.11"
# dependencies = ["redsun[pyqt]>=0.14", "fastcs[epicspva]", "ophyd-async[pva]"]
# ///
"""The session built in the "Writing a service with FastCS" tutorial."""

from __future__ import annotations

from collections.abc import Iterator, Mapping  # noqa: TC003
from typing import Annotated, Any, ClassVar, Protocol

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator  # noqa: TC002
from ophyd_async.core import Device, SignalRW
from ophyd_async.fastcs.core import fastcs_connector
from psygnal import Signal
from qtpy.QtWidgets import QVBoxLayout, QWidget

from redsun import (
    AsDevice,
    AsPresenter,
    AsService,
    AsView,
    Declare,
    DeviceMapping,
    DevicesOf,
    Launch,
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


# --8<-- [start:device]
class MyStage(Device):
    position: SignalRW[float]

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(name=name, connector=fastcs_connector(prefix, self))


# --8<-- [end:device]
class HasPosition(Protocol):
    position: SignalRW[float]


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

    def walk(self, steps: int = 5, size: float = 1.0) -> MsgGenerator[None]:
        for _ in range(steps):
            position = yield from bps.rd(self.stage.position)
            yield from bps.mv(self.stage.position, position + size)

    @provides
    def spec(self) -> PlanSpec:
        return self._spec

    @slot
    def run(self, values: dict[str, Any]) -> None:
        resolved = resolve_arguments(self._spec, values, self.devices)
        args, kwargs = collect_arguments(self._spec, resolved)
        future = self.engine(self.walk(*args, **kwargs))
        future.add_done_callback(lambda _: self.sig_finished.emit())


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


# --8<-- [start:session]
class FastcsSession(QtSession):
    config: ClassVar[Mapping[str, Any]] = {"services": {"transport": "pv-access"}}

    stage_service: Annotated[
        AsService, Launch("stage_fastcs", ready="stage ready", prefix="STAGE:")
    ]
    stage: Annotated[AsDevice[MyStage], Declare(service="stage_service")]
    scan_ctrl: AsPresenter[ScanPresenter]
    scan_view: AsView[ScanView]

    def wire(self) -> Iterator[Link]:
        yield self.scan_view.sig_run, self.scan_ctrl.run
        yield self.scan_ctrl.sig_finished, self.scan_view.on_finished


if __name__ == "__main__":
    FastcsSession().run()
# --8<-- [end:session]
