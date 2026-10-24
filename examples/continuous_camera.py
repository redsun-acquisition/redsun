"""The session of the guide "How to write a camera for continuous acquisition"."""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence  # noqa: TC003
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
from bluesky.protocols import HasHints, Reading
from bluesky.utils import MsgGenerator  # noqa: TC002
from ophyd_async.core import (
    AsyncStatus,
    DetectorAcquireLogic,
    DetectorDataLogic,
    DetectorTriggerLogic,
    Device,
    PathProvider,
    SignalR,
    SignalRW,
    StandardDetector,
    StandardReadable,
    StandardReadableFormat,
    StreamResourceDataProvider,
    StreamResourceInfo,
    TriggerInfo,
    wait_for_value,
    walk_devices,
)
from ophyd_async.epics.core import epics_signal_r, epics_signal_rw
from psygnal import Signal

from redsun import AsDevice, AsPresenter, AsService, Declare, Launch, Link, slot
from redsun.qt import QtSession


# --8<-- [start:acquire-for-plan]
@dataclass
class AcquireForPlan:
    """Start a camera for a plan, and leave it as the plan found it."""

    acquire: SignalRW[bool]
    was_acquiring: bool = False

    async def start(self) -> None:
        self.was_acquiring = await self.acquire.get_value()
        if not self.was_acquiring:
            await self.acquire.set(True)

    async def restore(self) -> None:
        if not self.was_acquiring:
            await self.acquire.set(False)


# --8<-- [end:acquire-for-plan]
# --8<-- [start:writer-logics]
@dataclass
class CaptureTrigger(DetectorTriggerLogic):
    num_capture: SignalRW[int]

    async def prepare_internal(
        self, num: int, livetime: float, deadtime: float
    ) -> None:
        await self.num_capture.set(num)


@dataclass
class CaptureAcquire(DetectorAcquireLogic):
    capture: SignalRW[bool]
    num_capture: SignalRW[int]
    acquisition: AcquireForPlan

    async def ensure_ready(self) -> None:
        await self.acquisition.start()
        await self.capture.set(False)

    async def start_acquiring(self) -> None:
        await self.capture.set(True)

    async def wait_for_idle(self) -> None:
        if await self.num_capture.get_value():
            await wait_for_value(self.capture, False, timeout=None)
        else:
            await self.capture.set(False)

    async def ensure_stopped(self) -> None:
        await self.capture.set(False)
        await self.acquisition.restore()


@dataclass
class CaptureData(DetectorDataLogic):
    image: SignalR[np.ndarray]
    file_path: SignalRW[str]
    num_captured: SignalR[int]
    path_provider: PathProvider

    async def prepare_unbounded(self, datakey_name: str) -> StreamResourceDataProvider:
        info = self.path_provider(datakey_name)
        uri = f"{info.directory_uri}{info.filename}.h5"
        await self.file_path.set(uri)
        await wait_for_value(self.num_captured, 0, timeout=5)
        frame = (await self.image.describe())[self.image.name]
        shape = tuple(size or 0 for size in frame["shape"])
        return StreamResourceDataProvider(
            uri=uri,
            resources=[
                StreamResourceInfo(
                    data_key=datakey_name,
                    shape=shape,
                    chunk_shape=(1, *shape),
                    dtype_numpy=frame["dtype_numpy"],
                    parameters={"dataset": "/data"},
                )
            ],
            mimetype="application/x-hdf5",
            collections_written_signal=self.num_captured,
        )


# --8<-- [end:writer-logics]
# --8<-- [start:writer]
class CameraWriter(StandardDetector):
    """Write frames to a file while the camera acquires, and leave it acquiring."""

    def __init__(
        self, prefix: str, path_provider: PathProvider, name: str = ""
    ) -> None:
        self.acquire = epics_signal_rw(bool, f"pva://{prefix}Acquire")
        self.image = epics_signal_r(np.ndarray, f"pva://{prefix}Image")
        self.capture = epics_signal_rw(bool, f"pva://{prefix}Capture")
        self.num_capture = epics_signal_rw(int, f"pva://{prefix}NumCapture")
        self.file_path = epics_signal_rw(str, f"pva://{prefix}FilePath")
        self.num_captured = epics_signal_r(int, f"pva://{prefix}NumCaptured")
        super().__init__(name=name)
        self.add_detector_logics(
            CaptureTrigger(self.num_capture),
            CaptureAcquire(
                self.capture, self.num_capture, AcquireForPlan(self.acquire)
            ),
            CaptureData(self.image, self.file_path, self.num_captured, path_provider),
        )


# --8<-- [end:writer]
# --8<-- [start:camera]
class Camera(StandardReadable):
    """A camera that acquires continuously: plans read its latest frame."""

    def __init__(self, prefix: str, name: str = "") -> None:
        with self.add_children_as_readables(
            StandardReadableFormat.HINTED_UNCACHED_SIGNAL
        ):
            self.image = epics_signal_r(np.ndarray, f"pva://{prefix}Image")
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.exposure = epics_signal_rw(float, f"pva://{prefix}Exposure")
        self.acquire = epics_signal_rw(bool, f"pva://{prefix}Acquire")
        self.image_count = epics_signal_r(int, f"pva://{prefix}ImageCount")
        self.acquisition = AcquireForPlan(self.acquire)
        super().__init__(name=name)

    @AsyncStatus.wrap
    async def stage(self) -> None:
        await self.acquisition.start()
        await super().stage()

    @AsyncStatus.wrap
    async def unstage(self) -> None:
        await super().unstage()
        await self.acquisition.restore()

    @AsyncStatus.wrap
    async def trigger(self) -> None:
        seen = await self.image_count.get_value(cached=False)
        # frame seen + 1 may have started its exposure before this call
        await wait_for_value(self.image_count, lambda n: n >= seen + 2, timeout=10)


# --8<-- [end:camera]
# --8<-- [start:write-frames]
def write_frames(
    writers: Sequence[StandardDetector], frames: int
) -> MsgGenerator[None]:
    """Write `frames` frames of each writer to a file while its camera runs."""

    def capture() -> MsgGenerator[None]:
        yield from bps.declare_stream(*writers, name="primary", collect=True)
        yield from bps.kickoff_all(*writers, wait=True)
        yield from bps.collect_while_completing(writers, writers, flush_period=0.5)

    def prepare_and_capture() -> MsgGenerator[None]:
        for writer in writers:
            yield from bps.prepare(
                writer, TriggerInfo(number_of_events=frames), wait=True
            )
        yield from bpp.run_wrapper(capture())

    yield from bpp.stage_wrapper(prepare_and_capture(), writers)


# --8<-- [end:write-frames]
# --8<-- [start:hinted-arrays]
def hinted_arrays(device: Device) -> list[SignalR[Any]]:
    """Return the hinted signals of `device` that hold arrays, such as images."""
    hinted = (
        set(device.hints.get("fields", [])) if isinstance(device, HasHints) else set()
    )
    return [
        signal
        for signal in walk_devices(device).values()
        if isinstance(signal, SignalR)
        and signal.name in hinted
        and signal.datatype is np.ndarray
    ]


# --8<-- [end:hinted-arrays]
# --8<-- [start:live-frames]
class LiveFrames:
    """Pass on the latest frame of every camera, at most `rate` times a second."""

    sig_frame = Signal(str, object)

    def __init__(self, name: str, rate: float = 10.0) -> None:
        self.name = name
        self.period = 1 / rate
        self.shown: dict[str, float] = {}

    @slot
    def show(self, reading: dict[str, Reading[Any]]) -> None:
        now = time.monotonic()
        for key, value in reading.items():
            if now - self.shown.get(key, 0.0) >= self.period:
                self.shown[key] = now
                self.sig_frame.emit(key, value["value"])


# --8<-- [end:live-frames]
# --8<-- [start:session]
class MyApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"services": {"transport": "pv-access"}}
    camera_service: Annotated[
        AsService, Launch("mylab.services.camera", ready="camera ready", prefix="CAM:")
    ]
    camera: Annotated[AsDevice[Camera], Declare(service="camera_service")]
    camera_writer: Annotated[AsDevice[CameraWriter], Declare(service="camera_service")]
    live: AsPresenter[LiveFrames]

    def wire(self) -> Iterator[Link]:
        for device in self.devices.values():
            for signal in hinted_arrays(device):
                yield signal, self.live.show


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
