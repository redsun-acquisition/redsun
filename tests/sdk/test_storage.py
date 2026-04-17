"""Tests for redsun.storage (ophyd-async 0.17a2 data logic API)."""

from __future__ import annotations

import asyncio
from pathlib import Path, PurePath
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from ophyd_async.core import (
    DetectorDataLogic,
    StandardDetector,
    StaticFilenameProvider,
    StaticPathProvider,
    TriggerInfo,
    soft_signal_rw,
)

from redsun.storage import (
    DataWriter,
    SourceInfo,
    create_writer,
    handle_descriptor_metadata,
)
from redsun.storage._factory import WriterType
from redsun.storage.logics import (
    FrameWriterArmLogic,
    FrameWriterDataLogic,
    FrameWriterTriggerLogic,
    NDArrayInfo,
)
from redsun.storage.presenter import get_available_writers
from redsun.storage.protocols import HasMetadata, HasWriterLogic

# ---------------------------------------------------------------------------
# Minimal concrete DataWriter for tests (no local imports)
# ---------------------------------------------------------------------------


class _ConcreteDataWriter(DataWriter):
    """Minimal DataWriter subclass used across all storage tests."""

    def __init__(self) -> None:
        super().__init__()
        self._sources: dict[str, SourceInfo] = {}
        self._is_open = False
        self._written: dict[str, list[Any]] = {}
        self._path: PurePath | None = None

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

    def close(self) -> None:
        self._is_open = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_nd_array_info(
    height: int = 64,
    width: int = 64,
    x: int = 0,
    y: int = 0,
    dtype: str = "uint8",
) -> NDArrayInfo:
    x_sig = soft_signal_rw(int, initial_value=x)
    y_sig = soft_signal_rw(int, initial_value=y)
    h_sig = soft_signal_rw(int, initial_value=height)
    w_sig = soft_signal_rw(int, initial_value=width)
    dt_sig = soft_signal_rw(str, initial_value=dtype)
    await asyncio.gather(
        x_sig.connect(mock=False),
        y_sig.connect(mock=False),
        h_sig.connect(mock=False),
        w_sig.connect(mock=False),
        dt_sig.connect(mock=False),
    )
    return NDArrayInfo(x=x_sig, y=y_sig, height=h_sig, width=w_sig, numpy_dtype=dt_sig)


# ---------------------------------------------------------------------------
# SourceInfo
# ---------------------------------------------------------------------------


class TestSourceInfo:
    def test_defaults(self) -> None:
        info = SourceInfo(dtype_numpy="uint8", shape=(512, 512), capacity=None)
        assert info.capacity is None

    def test_fields(self) -> None:
        info = SourceInfo(dtype_numpy="float32", shape=(64, 128), capacity=10)
        assert info.dtype_numpy == "float32"
        assert info.shape == (64, 128)
        assert info.capacity == 10


# ---------------------------------------------------------------------------
# DataWriter base class behaviour
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# FrameWriterArmLogic
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# FrameWriterTriggerLogic
# ---------------------------------------------------------------------------


class TestFrameWriterTriggerLogic:
    async def test_prepare_internal_registers_source(self) -> None:
        info = await _make_nd_array_info(height=64, width=64)
        writer = _ConcreteDataWriter()
        logic = FrameWriterTriggerLogic(datakey_name="cam", writer=writer, info=info)
        await logic.prepare_internal(num=10, livetime=0.0, deadtime=0.0)
        assert "cam" in writer.sources
        src = writer.sources["cam"]
        assert src.shape == (64, 64)
        assert src.capacity == 10
        assert src.dtype_numpy == "uint8"

    async def test_prepare_internal_respects_roi_offset(self) -> None:
        info = await _make_nd_array_info(height=64, width=64, x=8, y=16)
        writer = _ConcreteDataWriter()
        logic = FrameWriterTriggerLogic(datakey_name="cam", writer=writer, info=info)
        await logic.prepare_internal(num=1, livetime=0.0, deadtime=0.0)
        assert writer.sources["cam"].shape == (64 - 16, 64 - 8)

    async def test_default_trigger_info_returns_zero_events(self) -> None:
        info = await _make_nd_array_info()
        writer = _ConcreteDataWriter()
        logic = FrameWriterTriggerLogic(datakey_name="cam", writer=writer, info=info)
        ti = await logic.default_trigger_info()
        assert isinstance(ti, TriggerInfo)
        assert ti.number_of_events == 0


# ---------------------------------------------------------------------------
# FrameWriterDataLogic
# ---------------------------------------------------------------------------


class TestFrameWriterDataLogic:
    def test_writer_property(self, tmp_path: Path) -> None:
        writer = _ConcreteDataWriter()
        pp = StaticPathProvider(StaticFilenameProvider("scan"), PurePath(tmp_path))
        info = NDArrayInfo(
            x=soft_signal_rw(int),
            y=soft_signal_rw(int),
            height=soft_signal_rw(int),
            width=soft_signal_rw(int),
            numpy_dtype=soft_signal_rw(str),
        )
        logic = FrameWriterDataLogic(writer=writer, info=info, path_provider=pp)
        assert logic.writer is writer

    def test_get_hinted_fields_returns_datakey(self, tmp_path: Path) -> None:
        writer = _ConcreteDataWriter()
        pp = StaticPathProvider(StaticFilenameProvider("scan"), PurePath(tmp_path))
        info = NDArrayInfo(
            x=soft_signal_rw(int),
            y=soft_signal_rw(int),
            height=soft_signal_rw(int),
            width=soft_signal_rw(int),
            numpy_dtype=soft_signal_rw(str),
        )
        logic = FrameWriterDataLogic(writer=writer, info=info, path_provider=pp)
        assert logic.get_hinted_fields("cam") == ["cam"]


# ---------------------------------------------------------------------------
# Smoke test 1 — FrameWriterDataLogic satisfies DetectorDataLogic
# ---------------------------------------------------------------------------


def test_writer_data_logic_is_detector_data_logic(tmp_path: Path) -> None:
    """FrameWriterDataLogic must satisfy the ophyd-async DetectorDataLogic protocol."""
    writer = _ConcreteDataWriter()
    pp = StaticPathProvider(StaticFilenameProvider("scan"), PurePath(tmp_path))
    info = NDArrayInfo(
        x=soft_signal_rw(int),
        y=soft_signal_rw(int),
        height=soft_signal_rw(int),
        width=soft_signal_rw(int),
        numpy_dtype=soft_signal_rw(str),
    )
    logic = FrameWriterDataLogic(writer=writer, info=info, path_provider=pp)
    assert isinstance(logic, DetectorDataLogic)


# ---------------------------------------------------------------------------
# Smoke test 2 — create_writer factory returns a DataWriter
# ---------------------------------------------------------------------------


def test_create_writer_returns_data_writer() -> None:
    """Factory must return a DataWriter subclass with correct mimetype."""
    writer = create_writer(WriterType.ZARR)
    assert isinstance(writer, DataWriter)
    assert writer.mimetype == "application/x-zarr"


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# handle_descriptor_metadata
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# get_available_writers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# ZarrDataWriter — import guard
# ---------------------------------------------------------------------------


class TestZarrDataWriterImportGuard:
    def test_import_error_without_acquire_zarr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import redsun.storage._zarr as zarr_mod

        monkeypatch.setattr(zarr_mod, "_ACQUIRE_ZARR_AVAILABLE", False)
        with pytest.raises(ImportError, match="acquire-zarr"):
            from redsun.storage._zarr import ZarrDataWriter

            ZarrDataWriter()


# ---------------------------------------------------------------------------
# StandardDetector compliance test
# ---------------------------------------------------------------------------


@pytest.fixture
async def detector_setup(
    tmp_path: Path,
) -> tuple[StandardDetector, _ConcreteDataWriter]:
    info = await _make_nd_array_info(height=64, width=64)
    writer = _ConcreteDataWriter()
    pp = StaticPathProvider(StaticFilenameProvider("scan"), PurePath(tmp_path))

    arm_logic = FrameWriterArmLogic(datakey_name="cam", writer=writer)
    trigger_logic = FrameWriterTriggerLogic(
        datakey_name="cam", writer=writer, info=info
    )
    data_logic = FrameWriterDataLogic(writer=writer, info=info, path_provider=pp)

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
