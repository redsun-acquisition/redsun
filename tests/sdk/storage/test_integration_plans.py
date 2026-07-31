"""RunEngine integration: async device writer + sync callback writer.

A StandardDetector built on the ophyd-async logic decomposition streams
frames to a BaseStorage sink, while a DocumentRouter callback consumes
Event documents from the same run and writes a derived (median) key
through the sync API.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import bluesky.plan_stubs as bps
import culsans
import numpy as np
import pytest
from event_model import DocumentRouter
from ophyd_async.core import (
    DetectorAcquireLogic,
    DetectorDataLogic,
    DetectorTriggerLogic,
    StandardDetector,
    StreamResourceDataProvider,
    TriggerInfo,
    soft_signal_rw,
)

from redsun.aio import run_coro
from redsun.engine import RunEngine
from redsun.storage import BaseStorage, FrameSink, SessionPathProvider, StreamSpec
from redsun.storage.backends._memory import MemoryIO

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path
    from typing import Any

    import numpy.typing as npt
    from bluesky.utils import MsgGenerator
    from event_model.documents import Event, EventDescriptor, RunStop
    from ophyd_async.core import PathInfo, StreamableDataProvider

    from redsun.storage._base import OpenStore

SHAPE = (4, 4)
DTYPE = "uint16"
NUM_FRAMES = 3


@dataclass
class DemoTriggerLogic(DetectorTriggerLogic):
    storage: BaseStorage
    datakey: str
    acquire: DemoAcquireLogic

    async def prepare_internal(
        self, num: int, livetime: float, deadtime: float
    ) -> None:
        self.storage.register(
            StreamSpec(data_key=self.datakey, shape=SHAPE, dtype=DTYPE, capacity=num)
        )
        self.acquire.num = num

    async def default_trigger_info(self) -> TriggerInfo:
        return TriggerInfo(number_of_events=NUM_FRAMES)


class DemoAcquireLogic(DetectorAcquireLogic):
    def __init__(self) -> None:
        self.sink: FrameSink | None = None
        self.num = 0
        self._task: asyncio.Task[None] | None = None

    async def ensure_ready(self) -> None:
        return None

    async def start_acquiring(self) -> None:
        assert self.sink is not None

        async def _push(sink: FrameSink, num: int) -> None:
            with contextlib.suppress(culsans.QueueShutDown):
                for i in range(num):
                    await sink.put(np.full(SHAPE, i, dtype=DTYPE))

        self._task = asyncio.create_task(_push(self.sink, self.num))

    async def wait_for_idle(self) -> None:
        if self._task is not None:
            await self._task

    async def ensure_stopped(self) -> None:
        if self._task is not None:
            await self._task
            self._task = None
        if self.sink is not None:
            self.sink.close()
            self.sink = None


@dataclass
class DemoDataLogic(DetectorDataLogic):
    storage: BaseStorage
    acquire: DemoAcquireLogic
    eager_open: bool = True
    spec: StreamSpec = field(init=False)

    async def prepare_unbounded(self, datakey_name: str) -> StreamableDataProvider:
        # spec was registered by DemoTriggerLogic.prepare_internal
        self.acquire.sink = self.storage.sink(datakey_name)
        if self.eager_open:
            # eager open: this detector owns its storage exclusively.
            # Shared-storage detectors must NOT open here - a sibling's
            # register would race the open and raise StoreStateError - # they rely on the drain's lazy open instead.
            await self.storage.open()
        self.spec = StreamSpec(
            data_key=datakey_name,
            shape=SHAPE,
            dtype=DTYPE,
            capacity=self.acquire.num,
        )
        return StreamResourceDataProvider(
            uri=self.storage.uri_for(datakey_name),
            resources=[self.storage.resource_info_for(self.spec)],
            mimetype=self.storage.mimetype,
            collections_written_signal=self.storage.signal_for(datakey_name),
        )


def make_detector(
    name: str, storage: BaseStorage, *, eager_open: bool = True
) -> StandardDetector:
    acquire = DemoAcquireLogic()
    trigger = DemoTriggerLogic(storage=storage, datakey=name, acquire=acquire)
    data = DemoDataLogic(storage=storage, acquire=acquire, eager_open=eager_open)
    det: StandardDetector = StandardDetector.__new__(StandardDetector)
    det.add_detector_logics(trigger, acquire, data)
    StandardDetector.__init__(det, name=name)
    return det


class LiveAcquireLogic(DetectorAcquireLogic):
    """Live-view acquire logic: streams to a buffer signal from stage time.

    The acquisition loop always updates the buffer signal for viewers and
    pushes into a `FrameSink` only while a write window is active (a sink
    exists). The
    write window ends when capacity shuts the queue down - the producer
    observes `QueueShutDown` and drops its sink, no `write_sig` involved.
    """

    def __init__(self, set_buffer: Callable[[npt.NDArray[Any]], None]) -> None:
        self.set_buffer = set_buffer
        self.pending_sink: FrameSink | None = None  # handed at prepare
        self.sink: FrameSink | None = None  # active from kickoff
        self.live_frames = 0
        self._live_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def ensure_ready(self) -> None:
        # stage: start live streaming, storage not involved
        if self._live_task is None:
            self._stop.clear()
            self._live_task = asyncio.create_task(self._live_loop())

    async def _live_loop(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = np.full(SHAPE, i % 100, dtype=DTYPE)
            self.set_buffer(frame)
            self.live_frames += 1
            if self.sink is not None:
                try:
                    await self.sink.put(frame)
                except culsans.QueueShutDown:
                    # capacity reached: write window over, back to pure live
                    self.sink = None
            i += 1
            await asyncio.sleep(0)

    async def start_acquiring(self) -> None:
        # kickoff: the write window becomes active - frames start flowing
        # into the sink obtained at prepare
        if self.pending_sink is not None:
            self.sink, self.pending_sink = self.pending_sink, None

    async def wait_for_idle(self) -> None:
        return None

    async def ensure_stopped(self) -> None:
        # unstage: stop live streaming
        self._stop.set()
        if self._live_task is not None:
            await self._live_task
            self._live_task = None
        for sink in (self.sink, self.pending_sink):
            if sink is not None:
                sink.close()
        self.sink = None
        self.pending_sink = None


@dataclass
class LiveTriggerLogic(DetectorTriggerLogic):
    storage: BaseStorage
    datakey: str

    async def prepare_internal(
        self, num: int, livetime: float, deadtime: float
    ) -> None:
        self.storage.register(
            StreamSpec(data_key=self.datakey, shape=SHAPE, dtype=DTYPE, capacity=num)
        )

    async def default_trigger_info(self) -> TriggerInfo:
        return TriggerInfo(number_of_events=NUM_FRAMES)


@dataclass
class LiveDataLogic(DetectorDataLogic):
    storage: BaseStorage
    acquire: LiveAcquireLogic

    async def prepare_unbounded(self, datakey_name: str) -> StreamableDataProvider:
        # live-view device: NO eager open - the store must materialise only
        # when the first frame is actually written (lazy open in the drain).
        # The sink is handed over here but only activated at kickoff.
        self.acquire.pending_sink = self.storage.sink(datakey_name)
        spec = StreamSpec(
            data_key=datakey_name, shape=SHAPE, dtype=DTYPE, capacity=NUM_FRAMES
        )
        return StreamResourceDataProvider(
            uri=self.storage.uri_for(datakey_name),
            resources=[self.storage.resource_info_for(spec)],
            mimetype=self.storage.mimetype,
            collections_written_signal=self.storage.signal_for(datakey_name),
        )


def make_live_detector(
    name: str, storage: BaseStorage, set_buffer: Callable[[npt.NDArray[Any]], None]
) -> tuple[StandardDetector, LiveAcquireLogic]:
    acquire = LiveAcquireLogic(set_buffer)
    trigger = LiveTriggerLogic(storage=storage, datakey=name)
    data = LiveDataLogic(storage=storage, acquire=acquire)
    det: StandardDetector = StandardDetector.__new__(StandardDetector)
    det.add_detector_logics(trigger, acquire, data)
    StandardDetector.__init__(det, name=name)
    return det, acquire


class MedianWriter(DocumentRouter):
    """Accumulates frames from Event docs; writes their median on stop."""

    def __init__(self, storage: BaseStorage, source_key: str) -> None:
        super().__init__()
        self.storage = storage
        self.source_key = source_key
        self.median_key = f"{source_key}_median"
        self.frames: list[npt.NDArray[Any]] = []
        self.sink: FrameSink | None = None

    def descriptor(self, doc: EventDescriptor) -> None:
        if self.source_key not in doc["data_keys"]:
            return
        data_key = doc["data_keys"][self.source_key]
        raw_shape = data_key["shape"]
        assert len(raw_shape) == 2
        assert raw_shape[0] is not None and raw_shape[1] is not None
        shape = (int(raw_shape[0]), int(raw_shape[1]))
        dtype = np.dtype(data_key.get("dtype_numpy", "<u2")).name
        self.storage.register(
            StreamSpec(data_key=self.median_key, shape=shape, dtype=dtype, capacity=1)
        )
        self.sink = self.storage.sink(self.median_key)

    def event(self, doc: Event) -> Event:
        if self.source_key in doc["data"]:
            self.frames.append(np.asarray(doc["data"][self.source_key]))
        return doc

    def stop(self, doc: RunStop) -> None:
        if self.sink is None or not self.frames:
            return
        stack = np.stack(self.frames, axis=0)
        median = np.median(stack, axis=0).astype(stack.dtype)
        self.sink.put_nowait(median)
        self.sink.close()


@pytest.fixture
def io() -> MemoryIO:
    return MemoryIO()


@pytest.fixture
def storage(io: MemoryIO, tmp_path: Path) -> BaseStorage:
    provider = SessionPathProvider(base_dir=tmp_path, session="integration")
    return BaseStorage(io=io, path_provider=provider)


def test_plan_with_device_and_callback_writers(
    storage: BaseStorage, io: MemoryIO
) -> None:
    engine = RunEngine()
    det = make_detector("det", storage)

    async def _make_signal() -> Any:
        return soft_signal_rw(
            np.ndarray, initial_value=np.zeros(SHAPE, dtype=DTYPE), name="buf"
        )

    buf = run_coro(_make_signal())
    callback = MedianWriter(storage, source_key="buf")
    engine.subscribe(callback)

    def plan() -> MsgGenerator[None]:
        yield from bps.open_run()
        # scan-like segment: frames travel as Event documents
        yield from bps.declare_stream(buf, name="scan")
        for i in range(NUM_FRAMES):
            yield from bps.abs_set(buf, np.full(SHAPE, i, dtype=DTYPE), wait=True)
            yield from bps.trigger_and_read([buf], name="scan")
        # write window: standard bounded fly segment
        yield from bps.stage_all(det)
        yield from bps.prepare(det, TriggerInfo(number_of_events=NUM_FRAMES), wait=True)
        # pre-declare the collect stream: StandardDetector's describe_collect
        # is singly-nested (WritesStreamAssets), which collect() requires to
        # have been pre-declared via declare_stream(collect=True)
        yield from bps.declare_stream(det, name="primary", collect=True)
        yield from bps.kickoff_all(det, wait=True)
        yield from bps.complete_all(det, wait=True)
        yield from bps.collect(det, name="primary")
        yield from bps.unstage_all(det)
        yield from bps.close_run()

    engine(plan()).result(timeout=30)
    # deterministic settle: close() awaits any drain still flushing
    run_coro(storage.close())

    assert len(io.stores) == 1
    store = io.stores[0]
    # device wrote NUM_FRAMES raw frames through the async API
    assert [f[0, 0] for f in store.arrays["det"]] == list(range(NUM_FRAMES))
    # callback wrote exactly one median frame through the sync API
    assert len(store.arrays["buf_median"]) == 1
    expected = np.median(
        np.stack([np.full(SHAPE, i, dtype=DTYPE) for i in range(NUM_FRAMES)]), axis=0
    ).astype(DTYPE)
    np.testing.assert_array_equal(store.arrays["buf_median"][0], expected)


def test_two_devices_share_one_storage(storage: BaseStorage, io: MemoryIO) -> None:
    """Two detectors share one BaseStorage: one store, one path, both keys.

    Shared-storage detectors must rely on lazy open (``eager_open=False``):
    an eager open at prepare would race the sibling's registration.
    """
    engine = RunEngine()
    det_a = make_detector("det_a", storage, eager_open=False)
    det_b = make_detector("det_b", storage, eager_open=False)

    def plan() -> MsgGenerator[None]:
        yield from bps.open_run()
        yield from bps.stage_all(det_a, det_b)
        yield from bps.prepare(
            det_a, TriggerInfo(number_of_events=NUM_FRAMES), wait=True
        )
        yield from bps.prepare(
            det_b, TriggerInfo(number_of_events=NUM_FRAMES), wait=True
        )
        yield from bps.declare_stream(det_a, name="stream_a", collect=True)
        yield from bps.declare_stream(det_b, name="stream_b", collect=True)
        yield from bps.kickoff_all(det_a, det_b, wait=True)
        yield from bps.complete_all(det_a, det_b, wait=True)
        yield from bps.collect(det_a, name="stream_a")
        yield from bps.collect(det_b, name="stream_b")
        yield from bps.unstage_all(det_a, det_b)
        yield from bps.close_run()

    engine(plan()).result(timeout=30)
    run_coro(storage.close())

    # exactly one backend store opened for the shared burst, closed once
    assert len(io.stores) == 1
    store = io.stores[0]
    assert sum(1 for call in store.calls if call == ("close", "")) == 1
    # both device keys landed in the same store with full capacity
    assert [f[0, 0] for f in store.arrays["det_a"]] == list(range(NUM_FRAMES))
    assert [f[0, 0] for f in store.arrays["det_b"]] == list(range(NUM_FRAMES))
    # the open saw both specs: the shared burst carries one path snapshot
    assert set(store.specs.keys()) == {"det_a", "det_b"}


def test_live_view_writes_only_during_write_window(tmp_path: Path) -> None:
    """Live view streams to the buffer signal; storage sees only the window.

    Frames flow to viewers from stage time with no store; a write-intent
    prepare opens the
    write window (sink lifecycle, no ``write_sig``); capacity ends it via
    ``QueueShutDown``; live streaming continues after; exactly one store
    exists at the end holding exactly ``capacity`` frames.
    """

    class StampingIO(MemoryIO):
        """Records how many live frames had flowed when the store opened."""

        def __init__(self) -> None:
            super().__init__()
            self.live_frames_at_open: int | None = None

        async def open(
            self, path: PathInfo, specs: Mapping[str, StreamSpec]
        ) -> OpenStore:
            self.live_frames_at_open = acquire.live_frames
            return await super().open(path, specs)

    io = StampingIO()
    provider = SessionPathProvider(base_dir=tmp_path, session="live")
    live_storage = BaseStorage(io=io, path_provider=provider)

    engine = RunEngine()
    buffer_updates: list[npt.NDArray[Any]] = []
    det, acquire = make_live_detector("cam", live_storage, buffer_updates.append)

    def plan() -> MsgGenerator[None]:
        yield from bps.open_run()
        yield from bps.stage_all(det)  # live streaming starts here
        # pure live-view period: frames flow, storage untouched
        yield from bps.sleep(0.05)
        # write window: a standard bounded fly segment, no write_sig
        yield from bps.prepare(det, TriggerInfo(number_of_events=NUM_FRAMES), wait=True)
        yield from bps.declare_stream(det, name="primary", collect=True)
        yield from bps.kickoff_all(det, wait=True)
        yield from bps.complete_all(det, wait=True)
        yield from bps.collect(det, name="primary")
        # live view continues after the window; still no new store
        yield from bps.sleep(0.05)
        yield from bps.unstage_all(det)  # live streaming stops here
        yield from bps.close_run()

    engine(plan()).result(timeout=30)
    run_coro(live_storage.close())

    # exactly one store, created lazily by the first written frame - after
    # live streaming had already produced frames without any storage
    assert len(io.stores) == 1
    assert io.live_frames_at_open is not None
    assert io.live_frames_at_open >= 1
    # the store holds exactly capacity frames despite live overshoot
    assert len(io.stores[0].arrays["cam"]) == NUM_FRAMES
    # live streaming outlived the write window: more frames flowed to the
    # buffer signal than were ever written
    assert acquire.live_frames == len(buffer_updates)
    assert acquire.live_frames > NUM_FRAMES
    # capacity ended the window from the producer's side: sink was dropped
    assert acquire.sink is None
