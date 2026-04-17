"""Tests for redsun.storage (ophyd-async 0.17a2 data logic API)."""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from itertools import count
from pathlib import Path, PurePath
from typing import Any

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
import numpy.typing as npt
import pytest
from bluesky.run_engine import RunEngine as BlueskyRunEngine
from ophyd_async.core import (
    DetectorDataLogic,
    SignalRW,
    StandardDetector,
    StaticFilenameProvider,
    StaticPathProvider,
    TriggerInfo,
    soft_signal_rw,
)
from ophyd_async.testing import assert_emitted

from redsun.storage import (
    DataWriter,
    SourceInfo,
    WriterType,
    create_writer,
    handle_descriptor_metadata,
)
from redsun.storage._zarr import ZarrDataWriter
from redsun.storage.logics import (
    FrameWriterArmLogic,
    FrameWriterDataLogic,
    FrameWriterTriggerLogic,
)
from redsun.storage.presenter import get_available_writers
from redsun.storage.protocols import HasMetadata, HasWriterLogic


class _ConcreteDataWriter(DataWriter):
    """Minimal DataWriter subclass used across all storage tests."""

    def __init__(self) -> None:
        super().__init__()
        self._sources: dict[str, SourceInfo] = {}
        self._is_open = False
        self._written: dict[str, list[Any]] = {}
        self._path: PurePath | None = None
        self._write_counter = count(1)

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def sources(self) -> dict[str, SourceInfo]:
        return self._sources

    @property
    def file_extension(self) -> str:
        return "test"

    @property
    def mimetype(self) -> str:
        return "application/x-test"

    def set_store_path(self, path: PurePath) -> None:
        self._path = path

    def is_path_set(self) -> bool:
        return self._path is not None

    def open(self) -> None:
        self._is_open = True

    def register(self, datakey: str, info: SourceInfo) -> None:
        self._sources[datakey] = info
        self._written.setdefault(datakey, [])

    def unregister(self, datakey: str) -> None:
        self._sources.pop(datakey, None)

    def write(self, datakey: str, data: npt.NDArray[Any]) -> None:
        self._written[datakey].append(data)
        self._update_count(next(self._write_counter))

    def close(self) -> None:
        self._is_open = False
        self._write_counter = count(1)


async def _make_trigger_logic_info(
    x: int = 0,
    y: int = 0,
    height: int = 64,
    width: int = 64,
    dtype: str = "uint8",
) -> tuple[SignalRW[np.ndarray[tuple[int, ...], np.dtype[np.uint64]]], SignalRW[str]]:

    shape_sig = soft_signal_rw(
        np.ndarray[tuple[int, ...], np.dtype[np.uint64]],
        initial_value=np.array([x, y, height, width], dtype=np.uint64),
    )
    dt_sig = soft_signal_rw(str, initial_value=dtype)

    await asyncio.gather(
        shape_sig.connect(mock=False),
        dt_sig.connect(mock=False),
    )
    return shape_sig, dt_sig


class TestSourceInfo:
    def test_defaults(self) -> None:
        info = SourceInfo(dtype_numpy="uint8", shape=(512, 512), capacity=None)
        assert info.capacity is None

    def test_fields(self) -> None:
        info = SourceInfo(dtype_numpy="float32", shape=(64, 128), capacity=10)
        assert info.dtype_numpy == "float32"
        assert info.shape == (64, 128)
        assert info.capacity == 10


class TestDataWriter:
    def test_initial_state(self) -> None:
        w = _ConcreteDataWriter()
        assert not w.is_open
        assert w.sources == {}

    def test_initial_path_not_set(self) -> None:
        w = _ConcreteDataWriter()
        assert not w.is_path_set()

    def test_set_store_path(self) -> None:
        w = _ConcreteDataWriter()
        w.set_store_path(Path("/tmp/test.test"))
        assert w.is_path_set()

    def test_image_counter_initial_value(self) -> None:
        w = _ConcreteDataWriter()
        assert w.image_counter is not None

    def test_register_adds_source(self) -> None:
        w = _ConcreteDataWriter()
        info = SourceInfo(dtype_numpy="uint16", shape=(4, 4), capacity=None)
        w.register("cam", info)
        assert "cam" in w.sources
        assert w.sources["cam"].shape == (4, 4)

    def test_unregister_removes_source(self) -> None:
        w = _ConcreteDataWriter()
        info = SourceInfo(dtype_numpy="uint8", shape=(2, 2), capacity=None)
        w.register("cam", info)
        w.unregister("cam")
        assert "cam" not in w.sources

    def test_open_sets_is_open(self) -> None:
        w = _ConcreteDataWriter()
        w.open()
        assert w.is_open

    def test_close_clears_is_open(self) -> None:
        w = _ConcreteDataWriter()
        w.open()
        w.close()
        assert not w.is_open

    def test_write_dispatches_to_backend(self) -> None:
        w = _ConcreteDataWriter()
        info = SourceInfo(dtype_numpy="uint8", shape=(2, 2), capacity=None)
        w.register("cam", info)
        w.open()
        frame = np.zeros((2, 2), dtype="uint8")
        w.write("cam", frame)
        assert len(w._written["cam"]) == 1
        assert w._written["cam"][0] is frame


class TestFrameWriterArmLogic:
    async def test_arm_opens_writer(self) -> None:
        writer = _ConcreteDataWriter()
        logic = FrameWriterArmLogic(datakey_name="cam", writer=writer)
        assert not writer.is_open
        await logic.arm()
        assert writer.is_open

    async def test_arm_is_idempotent(self) -> None:
        writer = _ConcreteDataWriter()
        logic = FrameWriterArmLogic(datakey_name="cam", writer=writer)
        await logic.arm()
        await logic.arm()
        assert writer.is_open

    async def test_disarm_unregisters_and_closes(self) -> None:
        writer = _ConcreteDataWriter()
        logic = FrameWriterArmLogic(datakey_name="cam", writer=writer)
        writer.register(
            "cam", SourceInfo(dtype_numpy="uint8", shape=(4, 4), capacity=1)
        )
        await logic.arm()
        assert writer.is_open
        await logic.disarm()
        assert "cam" not in writer.sources
        assert not writer.is_open

    async def test_disarm_leaves_open_when_sources_remain(self) -> None:
        writer = _ConcreteDataWriter()
        logic = FrameWriterArmLogic(datakey_name="cam", writer=writer)
        writer.register(
            "cam", SourceInfo(dtype_numpy="uint8", shape=(4, 4), capacity=1)
        )
        writer.register(
            "det", SourceInfo(dtype_numpy="uint8", shape=(4, 4), capacity=1)
        )
        await logic.arm()
        await logic.disarm()
        assert "det" in writer.sources
        assert writer.is_open

    async def test_wait_for_idle_is_noop(self) -> None:
        writer = _ConcreteDataWriter()
        logic = FrameWriterArmLogic(datakey_name="cam", writer=writer)
        await logic.wait_for_idle()


class TestFrameWriterTriggerLogic:
    async def test_prepare_internal_registers_source(self) -> None:
        shape, dtype = await _make_trigger_logic_info(height=64, width=64)
        writer = _ConcreteDataWriter()
        logic = FrameWriterTriggerLogic(
            datakey_name="cam", writer=writer, shape=shape, numpy_dtype=dtype
        )
        await logic.prepare_internal(num=10, livetime=0.0, deadtime=0.0)
        assert "cam" in writer.sources
        src = writer.sources["cam"]
        assert src.shape == (64, 64)
        assert src.capacity == 10
        assert src.dtype_numpy == "uint8"

    async def test_prepare_internal_respects_roi_offset(self) -> None:
        shape, dtype = await _make_trigger_logic_info(height=64, width=64, x=8, y=16)
        writer = _ConcreteDataWriter()
        logic = FrameWriterTriggerLogic(
            datakey_name="cam", writer=writer, shape=shape, numpy_dtype=dtype
        )
        await logic.prepare_internal(num=1, livetime=0.0, deadtime=0.0)
        assert writer.sources["cam"].shape == (64 - 16, 64 - 8)

    async def test_default_trigger_info_returns_zero_events(self) -> None:
        shape, dtype = await _make_trigger_logic_info()
        writer = _ConcreteDataWriter()
        logic = FrameWriterTriggerLogic(
            datakey_name="cam", writer=writer, shape=shape, numpy_dtype=dtype
        )
        ti = await logic.default_trigger_info()
        assert isinstance(ti, TriggerInfo)
        assert ti.number_of_events == 0


class TestFrameWriterDataLogic:
    def test_writer_property(self, tmp_path: Path) -> None:
        writer = _ConcreteDataWriter()
        pp = StaticPathProvider(StaticFilenameProvider("scan"), PurePath(tmp_path))
        logic = FrameWriterDataLogic(writer=writer, path_provider=pp)
        assert logic.writer is writer

    def test_get_hinted_fields_returns_datakey(self, tmp_path: Path) -> None:
        writer = _ConcreteDataWriter()
        pp = StaticPathProvider(StaticFilenameProvider("scan"), PurePath(tmp_path))
        logic = FrameWriterDataLogic(writer=writer, path_provider=pp)
        assert logic.get_hinted_fields("cam") == ["cam"]


def test_writer_data_logic_is_detector_data_logic(tmp_path: Path) -> None:
    """FrameWriterDataLogic must satisfy the ophyd-async DetectorDataLogic protocol."""
    writer = _ConcreteDataWriter()
    pp = StaticPathProvider(StaticFilenameProvider("scan"), PurePath(tmp_path))
    logic = FrameWriterDataLogic(writer=writer, path_provider=pp)
    assert isinstance(logic, DetectorDataLogic)


def test_create_writer_returns_data_writer() -> None:
    """Factory must return a DataWriter subclass with correct mimetype."""
    writer = create_writer(WriterType.ZARR)
    assert isinstance(writer, DataWriter)
    assert writer.mimetype == "application/x-zarr"


class TestHasWriterLogic:
    def test_device_with_writer_satisfies_protocol(self) -> None:
        class _FakeDevice:
            @property
            def writer(self) -> _ConcreteDataWriter:
                return _ConcreteDataWriter()

        assert isinstance(_FakeDevice(), HasWriterLogic)

    def test_device_without_writer_fails(self) -> None:
        class _NoWriter:
            pass

        assert not isinstance(_NoWriter(), HasWriterLogic)


class TestHasMetadata:
    def test_writer_satisfies_has_metadata(self) -> None:
        class _MetaWriter:
            def update_metadata(self, metadata: dict[str, Any]) -> None:
                pass

            def clear_metadata(self) -> None:
                pass

        assert isinstance(_MetaWriter(), HasMetadata)

    def test_object_without_update_metadata_fails(self) -> None:
        class _NoMeta:
            pass

        assert not isinstance(_NoMeta(), HasMetadata)


class TestHandleDescriptorMetadata:
    def _make_device(self, writer: _ConcreteDataWriter) -> object:
        class _FakeDevice:
            @property
            def writer(self) -> _ConcreteDataWriter:
                return writer

        return _FakeDevice()

    def test_skips_unknown_devices(self) -> None:
        doc = {"configuration": {"unknown": {"x": 1}}}
        handle_descriptor_metadata(doc, {})

    def test_skips_devices_without_writer(self) -> None:
        class _NoWriter:
            pass

        doc = {"configuration": {"motor": {"position": 1.5}}}
        handle_descriptor_metadata(doc, {"motor": _NoWriter()})

    def test_empty_configuration_is_noop(self) -> None:
        doc: dict[str, Any] = {"configuration": {}}
        handle_descriptor_metadata(doc, {})


class TestGetAvailableWriters:
    def test_returns_writer_grouped_by_mimetype(self) -> None:
        writer = _ConcreteDataWriter()

        class _FakeDevice:
            @property
            def writer(self) -> _ConcreteDataWriter:
                return writer

        result = get_available_writers({"cam": _FakeDevice()})
        assert "application/x-test" in result
        assert writer in result["application/x-test"].values()

    def test_deduplicates_shared_writer(self) -> None:
        writer = _ConcreteDataWriter()

        class _FakeDevice:
            @property
            def writer(self) -> _ConcreteDataWriter:
                return writer

        result = get_available_writers({"cam1": _FakeDevice(), "cam2": _FakeDevice()})
        assert len(result["application/x-test"]) == 1

    def test_skips_devices_without_writer(self) -> None:
        class _Plain:
            pass

        result = get_available_writers({"motor": _Plain()})
        assert result == {}


class TestZarrDataWriterImportGuard:
    def test_import_error_without_acquire_zarr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import redsun.storage._zarr as zarr_mod

        monkeypatch.setattr(zarr_mod, "_ACQUIRE_ZARR_AVAILABLE", False)
        with pytest.raises(ImportError, match="acquire-zarr"):
            from redsun.storage._zarr import ZarrDataWriter

            ZarrDataWriter()


@pytest.fixture
async def detector_setup(
    tmp_path: Path,
) -> tuple[StandardDetector, _ConcreteDataWriter]:
    shape, dtype = await _make_trigger_logic_info(height=64, width=64)
    writer = _ConcreteDataWriter()
    pp = StaticPathProvider(StaticFilenameProvider("scan"), PurePath(tmp_path))

    arm_logic = FrameWriterArmLogic(datakey_name="cam", writer=writer)
    trigger_logic = FrameWriterTriggerLogic(
        datakey_name="cam", writer=writer, shape=shape, numpy_dtype=dtype
    )
    data_logic = FrameWriterDataLogic(writer=writer, path_provider=pp)

    det = StandardDetector(name="cam")
    det.add_detector_logics(arm_logic, trigger_logic, data_logic)
    await det.connect(mock=True)
    return det, writer


class TestDetectorCompliance:
    async def test_is_standard_detector(
        self, detector_setup: tuple[StandardDetector, _ConcreteDataWriter]
    ) -> None:
        det, _ = detector_setup
        assert isinstance(det, StandardDetector)

    async def test_hints_include_datakey(
        self, detector_setup: tuple[StandardDetector, _ConcreteDataWriter]
    ) -> None:
        det, _ = detector_setup
        assert "cam" in det.hints["fields"]

    async def test_stage_succeeds(
        self, detector_setup: tuple[StandardDetector, _ConcreteDataWriter]
    ) -> None:
        det, _ = detector_setup
        await det.stage()

    async def test_prepare_registers_source_in_writer(
        self, detector_setup: tuple[StandardDetector, _ConcreteDataWriter]
    ) -> None:
        det, writer = detector_setup
        await det.stage()
        await det.prepare(TriggerInfo(number_of_events=1))
        assert "cam" in writer.sources
        src = writer.sources["cam"]
        assert src.shape == (64, 64)
        assert src.dtype_numpy == "uint8"
        assert src.capacity == 1

    async def test_prepare_sets_writer_path(
        self, detector_setup: tuple[StandardDetector, _ConcreteDataWriter]
    ) -> None:
        det, writer = detector_setup
        await det.stage()
        await det.prepare(TriggerInfo(number_of_events=1))
        assert writer.is_path_set()

    async def test_stage_then_prepare_then_arm_opens_writer(
        self, detector_setup: tuple[StandardDetector, _ConcreteDataWriter]
    ) -> None:
        det, writer = detector_setup
        await det.stage()
        await det.prepare(TriggerInfo(number_of_events=1))
        # Arm logic is exercised directly since trigger() would stall waiting
        # for the image counter signal to advance.
        arm_logic = det._arm_logic
        assert arm_logic is not None
        await arm_logic.arm()
        assert writer.is_open

    async def test_unstage_disarms_writer(
        self, detector_setup: tuple[StandardDetector, _ConcreteDataWriter]
    ) -> None:
        det, writer = detector_setup
        await det.stage()
        await det.prepare(TriggerInfo(number_of_events=1))
        # Arm before unstage so disarm has something to close.
        assert det._arm_logic is not None
        await det._arm_logic.arm()
        assert writer.is_open
        await det.unstage()
        assert not writer.is_open


@pytest.fixture
async def zarr_detector_setup(
    tmp_path: Path,
) -> tuple[StandardDetector, ZarrDataWriter]:
    shape, dtype = await _make_trigger_logic_info(height=64, width=64)
    writer = ZarrDataWriter()
    pp = StaticPathProvider(StaticFilenameProvider("scan"), PurePath(tmp_path))

    arm_logic = FrameWriterArmLogic(datakey_name="cam", writer=writer)
    trigger_logic = FrameWriterTriggerLogic(
        datakey_name="cam", writer=writer, shape=shape, numpy_dtype=dtype
    )
    data_logic = FrameWriterDataLogic(writer=writer, path_provider=pp)

    det = StandardDetector(name="cam")
    det.add_detector_logics(arm_logic, trigger_logic, data_logic)
    await det.connect(mock=True)
    return det, writer


class TestZarrDetectorLifecycle:
    """Zarr-backed detector lifecycle via arm/trigger/data logic classes."""

    async def test_prepare_registers_zarr_source(
        self, zarr_detector_setup: tuple[StandardDetector, ZarrDataWriter]
    ) -> None:
        det, writer = zarr_detector_setup
        await det.stage()
        await det.prepare(TriggerInfo(number_of_events=5))
        assert "cam" in writer.sources
        src = writer.sources["cam"]
        assert src.shape == (64, 64)
        assert src.capacity == 5

    async def test_arm_opens_zarr_stream(
        self, zarr_detector_setup: tuple[StandardDetector, ZarrDataWriter]
    ) -> None:
        det, writer = zarr_detector_setup
        await det.stage()
        await det.prepare(TriggerInfo(number_of_events=1))
        assert det._arm_logic is not None
        await det._arm_logic.arm()
        assert writer.is_open

    async def test_write_frame_and_full_lifecycle(
        self, zarr_detector_setup: tuple[StandardDetector, ZarrDataWriter]
    ) -> None:
        det, writer = zarr_detector_setup
        await det.stage()
        await det.prepare(TriggerInfo(number_of_events=1))
        assert det._arm_logic is not None
        await det._arm_logic.arm()
        assert writer.is_open

        frame = np.zeros((64, 64), dtype="uint8")
        writer.write("cam", frame)

        await det.unstage()
        assert not writer.is_open
        assert "cam" not in writer.sources


async def test_two_detectors_share_zarr_writer(tmp_path: Path) -> None:
    """Two StandardDetectors sharing one ZarrDataWriter write to the same store.

    Lifecycle (simulating a bluesky plan):
      stage -> prepare -> arm -> write -> unstage

    Key invariants verified:
    - Both sources are registered before the stream is opened.
    - The first arm() opens the stream; the second is a no-op.
    - After the first unstage(), the stream stays open (second source remains).
    - After the second unstage(), all sources are gone and the stream closes.
    """
    writer = ZarrDataWriter()
    pp = StaticPathProvider(StaticFilenameProvider("scan"), PurePath(tmp_path))

    shape1, dtype1 = await _make_trigger_logic_info(height=64, width=64)
    shape2, dtype2 = await _make_trigger_logic_info(height=32, width=32)

    arm1 = FrameWriterArmLogic(datakey_name="det1", writer=writer)
    trigger1 = FrameWriterTriggerLogic(
        datakey_name="det1", writer=writer, shape=shape1, numpy_dtype=dtype1
    )
    data1 = FrameWriterDataLogic(writer=writer, path_provider=pp)

    arm2 = FrameWriterArmLogic(datakey_name="det2", writer=writer)
    trigger2 = FrameWriterTriggerLogic(
        datakey_name="det2", writer=writer, shape=shape2, numpy_dtype=dtype2
    )
    data2 = FrameWriterDataLogic(writer=writer, path_provider=pp)

    det1 = StandardDetector(name="det1")
    det1.add_detector_logics(arm1, trigger1, data1)
    det2 = StandardDetector(name="det2")
    det2.add_detector_logics(arm2, trigger2, data2)

    await asyncio.gather(det1.connect(mock=True), det2.connect(mock=True))

    # ── stage ──────────────────────────────────────────────────────────────
    await det1.stage()
    await det2.stage()

    # ── prepare: both sources must be registered before the first arm ──────
    await det1.prepare(TriggerInfo(number_of_events=4))
    await det2.prepare(TriggerInfo(number_of_events=4))

    assert "det1" in writer.sources
    assert "det2" in writer.sources
    assert not writer.is_open

    # ── arm: first arm opens the zarr stream with both arrays configured ───
    await arm1.arm()
    assert writer.is_open

    await arm2.arm()  # no-op: stream already open
    assert writer.is_open

    # ── write one frame per detector ───────────────────────────────────────
    writer.write("det1", np.zeros((64, 64), dtype="uint8"))
    writer.write("det2", np.zeros((32, 32), dtype="uint8"))

    # ── unstage det1: unregisters det1, stream stays open for det2 ────────
    await det1.unstage()
    assert "det1" not in writer.sources
    assert "det2" in writer.sources
    assert writer.is_open

    # ── unstage det2: last source gone → stream closes ────────────────────
    await det2.unstage()
    assert "det2" not in writer.sources
    assert not writer.is_open


class _SimAutoWriteArmLogic(FrameWriterArmLogic):
    """Extends FrameWriterArmLogic with automatic frame writing for fly scan tests.

    After arming (which opens the writer), a background task writes dummy zero
    frames at *delay* second intervals, pausing halfway through to split the
    emitted stream_datum documents into two batches (mirroring the SimBlobDetector
    fly-scan test pattern).
    """

    def __init__(
        self, datakey_name: str, writer: DataWriter, delay: float = 0.01
    ) -> None:
        super().__init__(datakey_name=datakey_name, writer=writer)
        self._delay = delay
        self._task: asyncio.Task[None] | None = None

    async def arm(self) -> None:
        await super().arm()
        self._task = asyncio.create_task(self._write_frames())

    async def wait_for_idle(self) -> None:
        if self._task is not None:
            await self._task

    async def disarm(self, on_unstage: bool) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await super().disarm()

    async def _write_frames(self) -> None:
        info = self.writer.sources.get(self.datakey_name)
        if info is None or info.capacity is None:
            return
        half = info.capacity // 2
        # first half: spaced out so they land before the mid-scan pause
        for _ in range(half):
            await asyncio.sleep(self._delay)
            self.writer.write(
                self.datakey_name, np.zeros(info.shape, dtype=info.dtype_numpy)
            )
        # pause so collect_while_completing flushes an intermediate batch;
        # must be > flush_period (0.1 s) so the wait times out once before completion
        await asyncio.sleep(0.2)
        # second half: written synchronously in one event-loop tick so they
        # land in a single batch regardless of OS timer granularity
        for _ in range(info.capacity - half):
            self.writer.write(
                self.datakey_name, np.zeros(info.shape, dtype=info.dtype_numpy)
            )


@pytest.fixture
def bluesky_re() -> BlueskyRunEngine:
    """Return a standard bluesky RunEngine on its own event loop."""
    loop = asyncio.new_event_loop()
    loop.set_debug(True)
    return BlueskyRunEngine({}, call_returns_result=True, loop=loop)


@pytest.fixture
async def fly_scan_det(
    tmp_path: Path,
) -> tuple[StandardDetector, _ConcreteDataWriter, _SimAutoWriteArmLogic]:
    shape, dtype = await _make_trigger_logic_info(height=32, width=32)
    writer = _ConcreteDataWriter()
    pp = StaticPathProvider(StaticFilenameProvider("scan"), PurePath(tmp_path))

    arm_logic = _SimAutoWriteArmLogic(datakey_name="cam", writer=writer)
    trigger_logic = FrameWriterTriggerLogic(
        datakey_name="cam", writer=writer, shape=shape, numpy_dtype=dtype
    )
    data_logic = FrameWriterDataLogic(writer=writer, path_provider=pp)

    det = StandardDetector(name="cam")
    det.add_detector_logics(arm_logic, trigger_logic, data_logic)
    await det.connect(mock=False)
    return det, writer, arm_logic


def test_fly_scan_lifecycle(
    fly_scan_det: tuple[StandardDetector, _ConcreteDataWriter, _SimAutoWriteArmLogic],
    bluesky_re: BlueskyRunEngine,
) -> None:
    """Fly scan plan lifecycle with FrameWriter logic classes and _ConcreteDataWriter.

    Verifies that the standard bluesky fly-scan protocol
    (stage → prepare → declare_stream → kickoff → collect_while_completing → unstage)
    produces the expected stream document sequence.

    The _SimAutoWriteArmLogic writes 4 frames with a mid-scan pause, causing
    collect_while_completing to flush two separate stream_datum batches.
    """
    det, _writer, _arm = fly_scan_det
    RE = bluesky_re

    docs: dict[str, list[Any]] = defaultdict(list)
    RE.subscribe(lambda name, doc: docs[name].append(doc))

    @bpp.stage_decorator([det])
    @bpp.run_decorator()
    def fly_plan():
        yield from bps.prepare(det, TriggerInfo(number_of_events=4), wait=True)
        yield from bps.declare_stream(det, name="primary")
        yield from bps.kickoff(det, wait=True)
        yield from bps.collect_while_completing(
            flyers=[det], dets=[det], flush_period=0.1
        )

    RE(fly_plan())
    assert_emitted(
        docs, start=1, descriptor=1, stream_resource=1, stream_datum=2, stop=1
    )
    assert docs["stream_datum"][0]["indices"] == {"start": 0, "stop": 2}
    assert docs["stream_datum"][1]["indices"] == {"start": 2, "stop": 4}
