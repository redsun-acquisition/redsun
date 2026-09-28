# /// script
# requires-python = ">=3.11"
# dependencies = ["redsun[pyqt]>=0.14", "h5py", "caproto", "ophyd-async[ca]"]
# ///
"""The session built in the "Putting a device behind a service" tutorial."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003
from typing import Annotated, Any, NewType, Protocol, runtime_checkable
from urllib.parse import urlsplit
from urllib.request import url2pathname

import bluesky.plan_stubs as bps
import bluesky.plans as bp
import h5py
import numpy as np
from bluesky.protocols import Readable  # noqa: TC002
from bluesky.utils import MsgGenerator  # noqa: TC002
from event_model import DocumentRouter, StreamResource
from ophyd_async.core import SignalRW, StandardReadable, soft_signal_rw
from ophyd_async.epics.core import EpicsDevice, PvSuffix
from ophyd_async.sim import SimBlobDetector  # noqa: TC002
from psygnal import Signal
from qtpy.QtGui import QImage, QPixmap
from qtpy.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

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


class MyStage(StandardReadable):
    def __init__(self, name: str = "", *, units: str = "mm") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, units=units)
        super().__init__(name=name)


class FastStage(StandardReadable):
    def __init__(self, name: str = "", *, units: str = "mm") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, units=units)
            self.speed = soft_signal_rw(float, initial_value=10.0)
        super().__init__(name=name)


# --8<-- [start:remote]
class RemoteStage(EpicsDevice):
    position: Annotated[SignalRW[float], PvSuffix("Position")]


# --8<-- [end:remote]
@runtime_checkable
class HasPosition(Protocol):
    position: SignalRW[float]


class StagePresenter:
    sig_moved = Signal(float)

    def __init__(
        self, name: str, *, stages: DevicesOf[HasPosition], step: float = 1.0
    ) -> None:
        self.name = name
        self.stage = stages["stage"]
        self.step = step

    @slot
    async def nudge(self) -> None:
        position = await self.stage.position.get_value()
        await self.stage.position.set(position + self.step)
        self.sig_moved.emit(position + self.step)


class StageView(QWidget):
    placement: Placement = Dock("left")
    sig_nudge = Signal()

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        button = QPushButton("Nudge")
        button.clicked.connect(self.sig_nudge.emit)
        self.label = QLabel("position: 0.0")
        layout = QVBoxLayout(self)
        layout.addWidget(button)
        layout.addWidget(self.label)

    @slot
    def show_position(self, position: float) -> None:
        self.label.setText(f"position: {position}")


class HomePresenter:
    sig_homed = Signal(float)

    def __init__(self, name: str, *, stages: DevicesOf[HasPosition]) -> None:
        self.name = name
        self.stages = stages

    @slot
    async def home(self) -> None:
        for stage in self.stages.values():
            await stage.position.set(0.0)
        self.sig_homed.emit(0.0)


class HomeView(QWidget):
    placement: Placement = Dock("left")
    sig_home = Signal()

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        button = QPushButton("Home")
        button.clicked.connect(self.sig_home.emit)
        QVBoxLayout(self).addWidget(button)


class ScanPresenter:
    sig_finished = Signal()

    def __init__(self, name: str, *, devices: DeviceMapping) -> None:
        self.name = name
        self.devices = devices
        self.engine = RunEngine()
        self._spec = create_plan_spec(self.walk, devices)

    def walk(
        self, stage: HasPosition, steps: int = 5, size: float = 1.0
    ) -> MsgGenerator[None]:
        for _ in range(steps):
            position = yield from bps.rd(stage.position)
            yield from bps.mv(stage.position, position + size)

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
    placement: Placement = Dock("right")
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


SnapSpec = NewType("SnapSpec", PlanSpec)


class CameraPresenter(DocumentRouter):
    sig_started = Signal(str)
    sig_finished = Signal()
    sig_frame = Signal(object)

    def __init__(
        self, name: str, *, cameras: DevicesOf[Readable[Any]], devices: DeviceMapping
    ) -> None:
        super().__init__()
        self.name = name
        self.camera = cameras["camera"]
        self.devices = devices
        self.engine = RunEngine()
        self.engine.subscribe(self)
        self._spec = SnapSpec(create_plan_spec(self.snap, devices))
        self._written: tuple[str, str] | None = None

    def snap(self, frames: int = 3) -> MsgGenerator[Any]:
        return (yield from bp.count([self.camera], num=frames))

    @provides
    def spec(self) -> SnapSpec:
        return self._spec

    @slot
    def run(self, values: dict[str, Any]) -> None:
        resolved = resolve_arguments(self._spec, values, self.devices)
        args, kwargs = collect_arguments(self._spec, resolved)
        self.sig_started.emit("snap")
        future = self.engine(self.snap(*args, **kwargs))
        future.add_done_callback(self.finish)

    def stream_resource(self, doc: StreamResource) -> StreamResource:
        if doc["data_key"] == "camera":
            self._written = (doc["uri"], doc["parameters"]["dataset"])
        return doc

    def finish(self, _: object) -> None:
        if self._written is not None:
            uri, dataset = self._written
            with h5py.File(url2pathname(urlsplit(uri).path), "r") as file:
                self.sig_frame.emit(file[dataset][-1])
        self.sig_finished.emit()


class CameraView(QWidget):
    placement: Placement = Dock("right")
    sig_run = Signal(dict)

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self.image = QLabel("No image yet")

    def setup(self, spec: SnapSpec) -> None:
        self.widget = create_plan_widget(spec, run_callback=self.ask_to_run)
        layout = QVBoxLayout(self)
        layout.addWidget(self.widget.group_box)
        layout.addWidget(self.image)

    def ask_to_run(self) -> None:
        self.widget.setEnabled(False)
        self.sig_run.emit(self.widget.parameters)

    @slot
    def show_frame(self, frame: object) -> None:
        values = np.asarray(frame, dtype=float)
        low, high = values.min(), values.max()
        grey = (255 * (values - low) / max(high - low, 1.0)).astype(np.uint8)
        height, width = grey.shape
        image = QImage(
            grey.tobytes(), width, height, width, QImage.Format.Format_Grayscale8
        )
        self.image.setPixmap(QPixmap.fromImage(image.copy()))

    @slot
    def on_finished(self) -> None:
        self.widget.setEnabled(True)


# --8<-- [start:session]
class FirstSession(QtSession):
    stage_ioc: Annotated[
        AsService,
        Launch("stage_ioc", ready="Server startup complete.", prefix="STAGE:"),
    ]
    stage: AsDevice[MyStage]
    fast_stage: AsDevice[FastStage]
    remote_stage: Annotated[AsDevice[RemoteStage], Declare(service="stage_ioc")]
    camera: AsDevice[SimBlobDetector]
    stage_ctrl: AsPresenter[StagePresenter]
    home_ctrl: AsPresenter[HomePresenter]
    scan_ctrl: AsPresenter[ScanPresenter]
    camera_ctrl: AsPresenter[CameraPresenter]
    stage_view: AsView[StageView]
    home_view: AsView[HomeView]
    scan_view: AsView[ScanView]
    camera_view: AsView[CameraView]

    def wire(self) -> Iterator[Link]:
        yield self.stage_view.sig_nudge, self.stage_ctrl.nudge
        yield self.stage_ctrl.sig_moved, self.stage_view.show_position
        yield self.home_view.sig_home, self.home_ctrl.home
        yield self.home_ctrl.sig_homed, self.stage_view.show_position
        yield self.scan_view.sig_run, self.scan_ctrl.run
        yield self.scan_ctrl.sig_finished, self.scan_view.on_finished
        yield self.camera_view.sig_run, self.camera_ctrl.run
        yield self.camera_ctrl.sig_started, self.path_provider.set_plan
        yield self.camera_ctrl.sig_frame, self.camera_view.show_frame
        yield self.camera_ctrl.sig_finished, self.camera_view.on_finished
        yield self.camera_ctrl.sig_finished, self.path_provider.reset_plan


if __name__ == "__main__":
    FirstSession().run()
# --8<-- [end:session]
