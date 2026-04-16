"""Tests for redsun.storage (ophyd-async 0.17a2 data logic API)."""

from __future__ import annotations

from pathlib import Path, PurePath
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from ophyd_async.core import DetectorDataLogic

from redsun.storage import (
    DataWriter,
    HasMetadata,
    HasWriterLogic,
    SourceInfo,
    WriterDataLogic,
    create_writer,
    get_available_writers,
    handle_descriptor_metadata,
)
from redsun.storage._factory import WriterType

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

    def open(self, path: PurePath) -> None:
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

    def test_image_counter_initial_value(self) -> None:
        w = _ConcreteDataWriter()
        # image_counter is a SignalR — it has a get_value coroutine
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
        w.open(Path("/tmp/test.test"))
        assert w.is_open

    def test_close_clears_is_open(self) -> None:
        w = _ConcreteDataWriter()
        w.open(Path("/tmp/test.test"))
        w.close()
        assert not w.is_open

    def test_write_dispatches_to_backend(self) -> None:
        w = _ConcreteDataWriter()
        info = SourceInfo(dtype_numpy="uint8", shape=(2, 2), capacity=None)
        w.register("cam", info)
        w.open(Path("/tmp/test.test"))
        frame = np.zeros((2, 2), dtype="uint8")
        w.write("cam", frame)
        assert len(w._written["cam"]) == 1
        assert w._written["cam"][0] is frame


# ---------------------------------------------------------------------------
# WriterDataLogic
# ---------------------------------------------------------------------------


class TestWriterDataLogic:
    def test_writer_property(self, tmp_path: Path) -> None:
        writer = _ConcreteDataWriter()
        logic = WriterDataLogic(writer, tmp_path, "scan")
        assert logic.writer is writer

    def test_update_source_registers_on_writer(self, tmp_path: Path) -> None:
        writer = _ConcreteDataWriter()
        logic = WriterDataLogic(writer, tmp_path, "scan")
        logic.update_source("cam", dtype_numpy="uint16", shape=(64, 64), capacity=10)
        assert "cam" in writer.sources
        assert writer.sources["cam"].shape == (64, 64)
        assert writer.sources["cam"].capacity == 10

    def test_get_hinted_fields_returns_source_keys(self, tmp_path: Path) -> None:
        writer = _ConcreteDataWriter()
        logic = WriterDataLogic(writer, tmp_path, "scan")
        logic.update_source("cam", dtype_numpy="uint8", shape=(4, 4))
        assert logic.get_hinted_fields("cam") == ["cam"]


# ---------------------------------------------------------------------------
# Smoke test 1 — WriterDataLogic satisfies DetectorDataLogic
# ---------------------------------------------------------------------------


def test_writer_data_logic_is_detector_data_logic(tmp_path: Path) -> None:
    """WriterDataLogic must satisfy the ophyd-async DetectorDataLogic protocol."""
    writer = _ConcreteDataWriter()
    logic = WriterDataLogic(writer, tmp_path, "scan")
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
    def test_device_with_writer_logic_satisfies_protocol(self) -> None:
        class _FakeDevice:
            @property
            def writer_logic(self) -> _ConcreteDataWriter:
                return _ConcreteDataWriter()

        assert isinstance(_FakeDevice(), HasWriterLogic)

    def test_device_without_writer_logic_fails(self) -> None:
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
            def writer_logic(self) -> _ConcreteDataWriter:
                return writer

        return _FakeDevice()

    def test_skips_unknown_devices(self) -> None:
        doc = {"configuration": {"unknown": {"x": 1}}}
        handle_descriptor_metadata(doc, {})

    def test_skips_devices_without_writer_logic(self) -> None:
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
            def writer_logic(self) -> _ConcreteDataWriter:
                return writer

        result = get_available_writers({"cam": _FakeDevice()})
        assert "application/x-test" in result
        assert writer in result["application/x-test"].values()

    def test_deduplicates_shared_writer(self) -> None:
        writer = _ConcreteDataWriter()

        class _FakeDevice:
            @property
            def writer_logic(self) -> _ConcreteDataWriter:
                return writer

        result = get_available_writers({"cam1": _FakeDevice(), "cam2": _FakeDevice()})
        assert len(result["application/x-test"]) == 1

    def test_skips_devices_without_writer_logic(self) -> None:
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
