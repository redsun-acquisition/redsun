"""Benchmark: acquire-zarr backend under live view + disk storage load.

Scenario
--------
Two ``StandardDetector``s share one ``BaseStorage`` backed by
``AcquireZarrIO`` (real disk I/O). Each detector's acquire loop does, per
frame, exactly what the mimir live-view pattern prescribes:

1. update its buffer signal (live view) — the plan ``bps.monitor``s the
   signal, so every update synchronously emits an Event document through
   the RunEngine, where a processing callback consumes it inline;
2. ``await sink.put(frame)`` (disk path) — frames flow through the bounded
   culsans queue into the per-key drain, which writes to the zarr store.

Both paths run on the engine's event loop, so the benchmark surfaces their
contention: callback processing time is stolen from the drains, and drain
backpressure stalls the producers.

Instrumented metrics and how to read them are described in ``README.md``.

Run with::

    uv run python benchmarks/bench_acquire_zarr.py --frames 200 --shape 512 512
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import bluesky.plan_stubs as bps
import culsans
import numpy as np
from event_model import DocumentRouter
from ophyd_async.core import (
    DetectorAcquireLogic,
    DetectorDataLogic,
    DetectorTriggerLogic,
    StandardDetector,
    StreamResourceDataProvider,
    TriggerInfo,
    soft_signal_r_and_setter,
)

from redsun.aio import run_coro
from redsun.engine import RunEngine
from redsun.storage import BaseStorage, FrameSink, SessionPathProvider, StreamSpec
from redsun.storage.backends._acquire_zarr import AcquireZarrIO

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any

    import numpy.typing as npt
    from bluesky.utils import MsgGenerator
    from event_model.documents import Event
    from ophyd_async.core import SignalR, StreamableDataProvider

FRAME_POOL_SIZE = 16


@dataclass
class ProducerStats:
    """Per-detector timings collected inside the acquire loop."""

    frames: int = 0
    buffer_time: float = 0.0
    buffer_max: float = 0.0
    put_time: float = 0.0
    put_max: float = 0.0


@dataclass
class BenchTriggerLogic(DetectorTriggerLogic):
    """Registers the stream spec at prepare time."""

    storage: BaseStorage
    datakey: str
    shape: tuple[int, int]
    dtype: str
    acquire: BenchAcquireLogic

    async def prepare_internal(
        self, num: int, livetime: float, deadtime: float
    ) -> None:
        """Register the stream and forward the frame budget to the producer."""
        self.storage.register(
            StreamSpec(
                data_key=self.datakey,
                shape=self.shape,
                dtype=self.dtype,
                capacity=num,
            )
        )
        self.acquire.num = num

    async def default_trigger_info(self) -> TriggerInfo:
        """Fallback trigger info (unused: the plan always prepares)."""
        return TriggerInfo(number_of_events=1)


class BenchAcquireLogic(DetectorAcquireLogic):
    """Producer emulating a camera: live emission + storage push per frame."""

    def __init__(
        self,
        set_buffer: Callable[[npt.NDArray[Any]], None],
        pool: Sequence[npt.NDArray[Any]],
        period: float,
        stats: ProducerStats,
    ) -> None:
        self.set_buffer = set_buffer
        self.pool = pool
        self.period = period
        self.stats = stats
        self.sink: FrameSink | None = None
        self.num = 0
        self._task: asyncio.Task[None] | None = None

    async def ensure_ready(self) -> None:
        """No hardware to reset."""
        return

    async def start_acquiring(self) -> None:
        """Kickoff: start the frame loop."""
        self._task = asyncio.create_task(self._acquire_loop())

    async def _acquire_loop(self) -> None:
        sink = self.sink
        assert sink is not None
        stats = self.stats
        pool = self.pool
        with contextlib.suppress(culsans.QueueShutDown):
            for i in range(self.num):
                frame = pool[i % FRAME_POOL_SIZE]

                start = time.perf_counter()
                self.set_buffer(frame)  # live path: monitor event + callback
                elapsed = time.perf_counter() - start
                stats.buffer_time += elapsed
                stats.buffer_max = max(stats.buffer_max, elapsed)

                start = time.perf_counter()
                await sink.put(frame)  # disk path: bounded queue -> drain
                elapsed = time.perf_counter() - start
                stats.put_time += elapsed
                stats.put_max = max(stats.put_max, elapsed)

                stats.frames += 1
                if self.period > 0.0:
                    await asyncio.sleep(self.period)

    async def wait_for_idle(self) -> None:
        """Wait for the frame loop to finish."""
        if self._task is not None:
            await self._task

    async def ensure_stopped(self) -> None:
        """Unstage: finish the loop and end the write window."""
        if self._task is not None:
            await self._task
            self._task = None
        if self.sink is not None:
            self.sink.close()
            self.sink = None


@dataclass
class BenchDataLogic(DetectorDataLogic):
    """Hands the sink over at prepare; lazy open (shared storage)."""

    storage: BaseStorage
    acquire: BenchAcquireLogic
    shape: tuple[int, int]
    dtype: str

    async def prepare_unbounded(self, datakey_name: str) -> StreamableDataProvider:
        """Create the sink and build the stream data provider."""
        self.acquire.sink = self.storage.sink(datakey_name)
        spec = StreamSpec(
            data_key=datakey_name,
            shape=self.shape,
            dtype=self.dtype,
            capacity=self.acquire.num,
        )
        return StreamResourceDataProvider(
            uri=self.storage.uri_for(datakey_name),
            resources=[self.storage.resource_info_for(spec)],
            mimetype=self.storage.mimetype,
            collections_written_signal=self.storage.signal_for(datakey_name),
        )


class ProcessingCallback(DocumentRouter):
    """Consumes monitor events inline and does configurable processing.

    Runs synchronously inside ``emit_sync`` on the engine loop — its
    cumulative time is stolen directly from producers and drains.
    """

    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode
        self.events = 0
        self.processing_time = 0.0
        self._background: npt.NDArray[Any] | None = None

    def event(self, doc: Event) -> Event:
        """Process one monitor event according to the selected mode."""
        start = time.perf_counter()
        for value in doc["data"].values():
            frame = np.asarray(value)
            if self.mode == "light":
                # running background subtraction + basic statistics
                if self._background is None:
                    self._background = frame.astype(np.float32)
                corrected = frame.astype(np.float32) - self._background
                float(corrected.mean())
                float(corrected.std())
            elif self.mode == "heavy":
                # 2D FFT magnitude — deliberately expensive
                np.abs(np.fft.rfft2(frame.astype(np.float32)))
        self.events += 1
        self.processing_time += time.perf_counter() - start
        return doc


def make_detector(
    name: str,
    storage: BaseStorage,
    shape: tuple[int, int],
    dtype: str,
    pool: Sequence[npt.NDArray[Any]],
    period: float,
    stats: ProducerStats,
) -> tuple[StandardDetector, SignalR[np.ndarray]]:
    """Assemble one benchmark detector plus its live-view buffer signal."""

    async def _make_signal() -> tuple[SignalR[np.ndarray], Any]:
        return soft_signal_r_and_setter(
            np.ndarray, initial_value=pool[0], name=f"{name}_buffer"
        )

    buffer_signal, setter = run_coro(_make_signal())
    acquire = BenchAcquireLogic(setter, pool, period, stats)
    trigger = BenchTriggerLogic(
        storage=storage, datakey=name, shape=shape, dtype=dtype, acquire=acquire
    )
    data = BenchDataLogic(storage=storage, acquire=acquire, shape=shape, dtype=dtype)
    det: StandardDetector = StandardDetector.__new__(StandardDetector)
    det.add_detector_logics(trigger, acquire, data)
    StandardDetector.__init__(det, name=name)
    return det, buffer_signal


@dataclass
class BenchResult:
    """Aggregated benchmark output."""

    frames: int
    shape: tuple[int, int]
    dtype: str
    plan_time: float = 0.0
    flush_time: float = 0.0
    disk_bytes: int = 0
    producers: dict[str, ProducerStats] = field(default_factory=dict)
    callback_events: int = 0
    callback_time: float = 0.0

    def report(self) -> str:
        """Render the human-readable report."""
        frame_bytes = self.shape[0] * self.shape[1] * np.dtype(self.dtype).itemsize
        total_frames = sum(p.frames for p in self.producers.values())
        written_mb = total_frames * frame_bytes / 1e6
        total = self.plan_time + self.flush_time
        lines = [
            "",
            "=" * 68,
            (
                f"acquire-zarr benchmark — {total_frames} frames total, "
                f"{self.shape[0]}x{self.shape[1]} {self.dtype} "
                f"({frame_bytes / 1e6:.2f} MB/frame)"
            ),
            "=" * 68,
            f"plan wall time            : {self.plan_time:8.3f} s",
            f"final flush (close)       : {self.flush_time:8.3f} s",
            (
                f"effective throughput      : {total_frames / total:8.1f} frames/s "
                f"({written_mb / total:.1f} MB/s)"
            ),
            f"bytes on disk             : {self.disk_bytes / 1e6:8.1f} MB",
            "-" * 68,
        ]
        for name, stats in self.producers.items():
            per_frame_buf = stats.buffer_time / max(stats.frames, 1) * 1e3
            per_frame_put = stats.put_time / max(stats.frames, 1) * 1e3
            lines += [
                f"[{name}] frames produced    : {stats.frames}",
                (
                    f"[{name}] live emission      : {stats.buffer_time:8.3f} s total "
                    f"({per_frame_buf:.3f} ms/frame, max {stats.buffer_max * 1e3:.3f} ms)"
                ),
                (
                    f"[{name}] sink.put wait      : {stats.put_time:8.3f} s total "
                    f"({per_frame_put:.3f} ms/frame, max {stats.put_max * 1e3:.3f} ms)"
                ),
            ]
        lines += [
            "-" * 68,
            f"callback events processed : {self.callback_events}",
            (
                f"callback processing time  : {self.callback_time:8.3f} s "
                f"({self.callback_time / max(self.callback_events, 1) * 1e3:.3f} ms/event)"
            ),
            "=" * 68,
        ]
        return "\n".join(lines)


def run_benchmark(
    frames: int,
    shape: tuple[int, int],
    dtype: str,
    maxsize: int,
    fps: float,
    proc: str,
    base_dir: Path,
) -> BenchResult:
    """Execute one benchmark run and collect the metrics."""
    rng = np.random.default_rng(seed=42)
    pool = [
        rng.integers(0, np.iinfo(np.dtype(dtype)).max, size=shape).astype(dtype)
        for _ in range(FRAME_POOL_SIZE)
    ]
    period = 1.0 / fps if fps > 0 else 0.0

    provider = SessionPathProvider(base_dir=base_dir, session="benchmark")
    storage = BaseStorage(io=AcquireZarrIO(), path_provider=provider, maxsize=maxsize)
    result = BenchResult(frames=frames, shape=shape, dtype=dtype)

    engine = RunEngine()
    detectors: list[StandardDetector] = []
    buffers: list[SignalR[np.ndarray]] = []
    for name in ("det_a", "det_b"):
        stats = ProducerStats()
        result.producers[name] = stats
        det, buffer_signal = make_detector(
            name, storage, shape, dtype, pool, period, stats
        )
        detectors.append(det)
        buffers.append(buffer_signal)

    callback = ProcessingCallback(proc)
    engine.subscribe(callback)

    def plan() -> MsgGenerator[None]:
        yield from bps.open_run()
        # live view: every buffer update becomes a monitor Event document
        for buffer_signal in buffers:
            yield from bps.monitor(buffer_signal, name=f"live_{buffer_signal.name}")
        yield from bps.stage_all(*detectors)
        for det in detectors:
            yield from bps.prepare(det, TriggerInfo(number_of_events=frames), wait=True)
        for det in detectors:
            yield from bps.declare_stream(det, name=f"write_{det.name}", collect=True)
        yield from bps.kickoff_all(*detectors, wait=True)
        yield from bps.complete_all(*detectors, wait=True)
        for det in detectors:
            yield from bps.collect(det, name=f"write_{det.name}")
        for buffer_signal in buffers:
            yield from bps.unmonitor(buffer_signal)
        yield from bps.unstage_all(*detectors)
        yield from bps.close_run()

    start = time.perf_counter()
    engine(plan()).result(timeout=3600)
    result.plan_time = time.perf_counter() - start

    start = time.perf_counter()
    run_coro(storage.close())
    result.flush_time = time.perf_counter() - start

    result.callback_events = callback.events
    result.callback_time = callback.processing_time
    result.disk_bytes = sum(
        f.stat().st_size for f in base_dir.rglob("*") if f.is_file()
    )
    return result


def main() -> int:
    """Parse arguments, run the benchmark, print the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=200, help="frames per detector")
    parser.add_argument(
        "--shape", type=int, nargs=2, default=(512, 512), help="frame shape (h w)"
    )
    parser.add_argument("--dtype", default="uint16", help="frame dtype")
    parser.add_argument(
        "--maxsize", type=int, default=100, help="per-key frame queue bound"
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=0.0,
        help="producer pacing in frames/s (0 = free-running)",
    )
    parser.add_argument(
        "--proc",
        choices=("none", "light", "heavy"),
        default="light",
        help="callback processing mode",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="output directory (default: a temporary directory, deleted afterwards)",
    )
    parser.add_argument(
        "--keep", action="store_true", help="keep the zarr output on disk"
    )
    args = parser.parse_args()

    base_dir = args.base_dir or Path(tempfile.mkdtemp(prefix="redsun-bench-"))
    try:
        result = run_benchmark(
            frames=args.frames,
            shape=(args.shape[0], args.shape[1]),
            dtype=args.dtype,
            maxsize=args.maxsize,
            fps=args.fps,
            proc=args.proc,
            base_dir=base_dir,
        )
        print(result.report())
        if args.keep:
            print(f"output kept at: {base_dir}")
    finally:
        if not args.keep and args.base_dir is None:
            shutil.rmtree(base_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
