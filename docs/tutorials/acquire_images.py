# /// script
# requires-python = ">=3.11"
# dependencies = ["redsun[pyqt]>=0.14", "h5py"]
# ///
"""The session built in the "Acquiring images" tutorial."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003
from typing import Any, NewType, Protocol
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
from ophyd_async.sim import SimBlobDetector  # noqa: TC002
from psygnal import Signal
from qtpy.QtGui import QImage, QPixmap
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget

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


# --8<-- [start:spec]
SnapSpec = NewType("SnapSpec", PlanSpec)


# --8<-- [end:spec]
# --8<-- [start:presenter]
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

    # --8<-- [start:plan]
    def snap(self, frames: int = 3) -> MsgGenerator[Any]:
        return (yield from bp.count([self.camera], num=frames))

    # --8<-- [end:plan]
    @provides
    def spec(self) -> SnapSpec:
        return self._spec

    # --8<-- [start:run]
    @slot
    def run(self, values: dict[str, Any]) -> None:
        resolved = resolve_arguments(self._spec, values, self.devices)
        args, kwargs = collect_arguments(self._spec, resolved)
        self.sig_started.emit("snap")
        future = self.engine(self.snap(*args, **kwargs))
        future.add_done_callback(self.finish)

    # --8<-- [end:run]
    # --8<-- [start:frame]
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

    # --8<-- [end:frame]


# --8<-- [end:presenter]
# --8<-- [start:view]
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

    # --8<-- [start:show]
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

    # --8<-- [end:show]
    @slot
    def on_finished(self) -> None:
        self.widget.setEnabled(True)


# --8<-- [end:view]
# --8<-- [start:session]
class AcquireSession(QtSession):
    stage: AsDevice[MyStage]
    camera: AsDevice[SimBlobDetector]
    scan_ctrl: AsPresenter[ScanPresenter]
    camera_ctrl: AsPresenter[CameraPresenter]
    scan_view: AsView[ScanView]
    camera_view: AsView[CameraView]

    def wire(self) -> Iterator[Link]:
        yield self.scan_view.sig_run, self.scan_ctrl.run
        yield self.scan_ctrl.sig_finished, self.scan_view.on_finished
        yield self.camera_view.sig_run, self.camera_ctrl.run
        yield self.camera_ctrl.sig_started, self.path_provider.set_plan
        yield self.camera_ctrl.sig_frame, self.camera_view.show_frame
        yield self.camera_ctrl.sig_finished, self.camera_view.on_finished
        yield self.camera_ctrl.sig_finished, self.path_provider.reset_plan


if __name__ == "__main__":
    AcquireSession().run()
# --8<-- [end:session]
