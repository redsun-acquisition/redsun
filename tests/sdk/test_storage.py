"""Smoke tests for redsun.storage."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
from bluesky.protocols import Descriptor, Reading

from redsun.device import Device
from redsun.storage import (
    AutoIncrementFilenameProvider,
    FrameSink,
    PathInfo,
    StaticFilenameProvider,
    StaticPathProvider,
    StorageDescriptor,
    StorageProxy,
    UUIDFilenameProvider,
    Writer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def current_date() -> str:
    return datetime.datetime.now().strftime("%Y_%m_%d")

class _MinimalDevice(Device):
    """Minimal concrete Device with no storage declared."""

    def __init__(self, name: str, /) -> None:
        super().__init__(name)

    def describe_configuration(self) -> dict[str, Descriptor]:
        return {}

    def read_configuration(self) -> dict[str, Reading[Any]]:
        return {}


class _StorageDevice(Device):
    """Device that explicitly opts into storage via StorageDescriptor."""

    storage = StorageDescriptor()

    def __init__(self, name: str, /) -> None:
        super().__init__(name)

    def describe_configuration(self) -> dict[str, Descriptor]:
        return {}

    def read_configuration(self) -> dict[str, Reading[Any]]:
        return {}


class _ConcreteWriter(Writer):
    """Minimal Writer subclass for testing the abstract base."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._frames: dict[str, list[Any]] = {}
        self._finalized = False

    @property
    def mimetype(self) -> str:
        return "application/x-test"

    def prepare(self, name: str, capacity: int = 0) -> FrameSink:
        self._frames.setdefault(name, [])
        self._store_path = "file:///tmp/test.zarr"
        return super().prepare(name, capacity)

    def kickoff(self) -> None:
        super().kickoff()

    def _write_frame(self, name: str, frame: Any) -> None:
        self._frames[name].append(frame)

    def _finalize(self) -> None:
        self._finalized = True


# ---------------------------------------------------------------------------
# StorageDescriptor
# ---------------------------------------------------------------------------


class TestStorageDescriptor:
    def test_descriptor_not_on_base_device(self) -> None:
        """Device base class must not have storage — it is opt-in."""
        assert "storage" not in Device.__dict__

    def test_descriptor_on_subclass(self) -> None:
        """Subclasses that declare StorageDescriptor must have it in __dict__."""
        assert isinstance(_StorageDevice.__dict__.get("storage"), StorageDescriptor)

    def test_default_raises(self) -> None:
        """Accessing storage before injection must raise AttributeError."""
        device = _StorageDevice("dev")
        with pytest.raises(AttributeError):
            _ = device.storage

    def test_uninjected_via_hasattr(self) -> None:
        """hasattr is the correct way to check whether storage is injected."""
        device = _StorageDevice("dev")
        assert not hasattr(device, "storage")

    def test_set_and_get(self) -> None:
        device = _StorageDevice("dev")
        mock_proxy = MagicMock(spec=StorageProxy)
        device.storage = mock_proxy
        assert device.storage is mock_proxy

    def test_independent_per_instance(self) -> None:
        """Each device instance must have its own storage slot."""
        dev_a = _StorageDevice("a")
        dev_b = _StorageDevice("b")
        dev_a.storage = MagicMock(spec=StorageProxy)
        assert not hasattr(dev_b, "storage")

    def test_class_access_returns_descriptor(self) -> None:
        assert isinstance(_StorageDevice.storage, StorageDescriptor)

    def test_device_without_storage_has_no_attribute(self) -> None:
        device = _MinimalDevice("dev")
        assert not hasattr(device, "storage")

    def test_set_name_derives_private_attribute(self) -> None:
        """__set_name__ must store the backing attribute as _{descriptor_name}."""

        class _NamedDevice(Device):
            writer = StorageDescriptor()

            def __init__(self, name: str, /) -> None:
                super().__init__(name)

            def describe_configuration(self) -> dict[str, Any]:
                return {}

            def read_configuration(self) -> dict[str, Any]:
                return {}

        assert _NamedDevice.writer._private_name == "_writer"
        device = _NamedDevice("dev")
        mock_proxy = MagicMock(spec=StorageProxy)
        device.writer = mock_proxy
        assert device.writer is mock_proxy

    def test_works_on_slotted_class(self) -> None:
        """StorageDescriptor must work on classes that define __slots__."""

        class _SlottedDevice:
            __slots__ = ("_name", "_storage")
            storage = StorageDescriptor()

            def __init__(self, name: str) -> None:
                self._name = name

        device = _SlottedDevice("slotted")
        assert not hasattr(device, "storage")
        mock_proxy = MagicMock(spec=StorageProxy)
        device.storage = mock_proxy
        assert device.storage is mock_proxy


# ---------------------------------------------------------------------------
# PathInfo
# ---------------------------------------------------------------------------


class TestPathInfo:
    def test_defaults(self) -> None:
        pi = PathInfo(store_uri="file:///data/scan.zarr", array_key="camera")
        assert pi.capacity == 0
        assert pi.mimetype_hint == "application/x-zarr"
        assert pi.extra == {}

    def test_custom_values(self) -> None:
        pi = PathInfo(
            store_uri="s3://bucket/scan.zarr",
            array_key="det",
            capacity=100,
            mimetype_hint="application/x-zarr",
            extra={"units": "nm"},
        )
        assert pi.store_uri == "s3://bucket/scan.zarr"
        assert pi.capacity == 100
        assert pi.extra == {"units": "nm"}


# ---------------------------------------------------------------------------
# FilenameProviders
# ---------------------------------------------------------------------------


class TestStaticFilenameProvider:
    def test_always_same(self, current_date: str) -> None:
        p = StaticFilenameProvider("scan001")
        assert p() == "_".join([current_date, "scan001"])
        assert p("camera") == "_".join([current_date, "scan001"])
        assert p() == "_".join([current_date, "scan001"])


class TestUUIDFilenameProvider:
    def test_returns_string(self, current_date: str) -> None:
        p = UUIDFilenameProvider()
        name = p()
        assert isinstance(name, str)

        # UUID4 canonical form plus date and underscore
        # should be 36 + 1 + len(current_date)
        assert len(name) == len(current_date) + 1 + 36

    def test_unique_per_call(self) -> None:
        p = UUIDFilenameProvider()
        assert p() != p()


class TestAutoIncrementFilenameProvider:
    def test_increments(self, current_date: str) -> None:
        p = AutoIncrementFilenameProvider(base="scan", max_digits=3, start=0)
        assert p() == "_".join([current_date, "scan_000"])
        assert p() == "_".join([current_date, "scan_001"])
        assert p() == "_".join([current_date, "scan_002"])

    def test_no_base(self, current_date: str) -> None:
        p = AutoIncrementFilenameProvider(max_digits=2, start=5)
        assert p() == "_".join([current_date, "05"])
        assert p() == "_".join([current_date, "06"])

    def test_overflow_raises(self) -> None:
        p = AutoIncrementFilenameProvider(max_digits=1, start=10)
        with pytest.raises(ValueError, match="exceeded maximum"):
            p()


# ---------------------------------------------------------------------------
# StaticPathProvider
# ---------------------------------------------------------------------------


class TestStaticPathProvider:
    def test_basic(self, current_date: str) -> None:
        fp = StaticFilenameProvider("scan001")
        pp = StaticPathProvider(fp, base_uri="file:///data")
        info = pp("camera")
        assert info.store_uri == "file:///data/" + "_".join([current_date, "scan001"])
        assert info.array_key == "camera"

    def test_trailing_slash_stripped(self, current_date: str) -> None:
        fp = StaticFilenameProvider("scan")
        pp = StaticPathProvider(fp, base_uri="file:///data/")
        info = pp("det")
        assert info.store_uri == "file:///data/" + "_".join([current_date, "scan"])

    def test_none_device_name(self, current_date: str) -> None:
        fp = StaticFilenameProvider("scan")
        pp = StaticPathProvider(fp, base_uri="file:///data")
        info = pp(None)
        # array_key falls back to filename when device_name is None
        assert info.array_key == "_".join([current_date, "scan"])

    def test_capacity_forwarded(self) -> None:
        fp = StaticFilenameProvider("s")
        pp = StaticPathProvider(fp, base_uri="file:///d", capacity=50)
        assert pp("x").capacity == 50


# ---------------------------------------------------------------------------
# Writer (via _ConcreteWriter)
# ---------------------------------------------------------------------------


class TestWriter:
    def _make_writer(self) -> _ConcreteWriter:
        return _ConcreteWriter("test_writer")

    def test_initial_state(self) -> None:
        w = self._make_writer()
        assert not w.is_open
        assert w.name == "test_writer"
        assert len(w.sources) == 0

    def test_update_source(self) -> None:
        w = self._make_writer()
        w.update_source("cam", np.dtype("uint8"), (512, 512))
        assert "cam" in w.sources
        assert w.sources["cam"].shape == (512, 512)
        assert w.sources["cam"].mimetype == "application/x-test"

    def test_update_source_while_open_raises(self) -> None:
        w = self._make_writer()
        w.update_source("cam", np.dtype("uint8"), (64, 64))
        w.prepare("cam")
        w.kickoff()
        with pytest.raises(RuntimeError, match="open"):
            w.update_source("cam2", np.dtype("uint8"), (64, 64))

    def test_prepare_returns_sink(self) -> None:
        w = self._make_writer()
        w.update_source("cam", np.dtype("uint8"), (4, 4))
        sink = w.prepare("cam")
        assert isinstance(sink, FrameSink)
        assert hasattr(sink, "write")
        assert hasattr(sink, "close")

    def test_prepare_unknown_source_raises(self) -> None:
        w = self._make_writer()
        with pytest.raises(KeyError):
            w.prepare("unknown")

    def test_kickoff_sets_open(self) -> None:
        w = self._make_writer()
        w.update_source("cam", np.dtype("uint8"), (4, 4))
        w.prepare("cam")
        w.kickoff()
        assert w.is_open

    def test_frame_written_via_sink(self) -> None:
        w = self._make_writer()
        w.update_source("cam", np.dtype("uint8"), (2, 2))
        sink = w.prepare("cam")
        w.kickoff()
        frame = np.zeros((2, 2), dtype="uint8")
        sink.write(frame)
        assert w.get_indices_written("cam") == 1
        assert w._frames["cam"][0] is frame

    def test_complete_finalizes_when_last_source_done(self) -> None:
        w = self._make_writer()
        w.update_source("cam", np.dtype("uint8"), (2, 2))
        w.prepare("cam")
        w.kickoff()
        w.complete("cam")
        assert not w.is_open
        assert w._finalized

    def test_two_sources_complete_sequence(self) -> None:
        w = self._make_writer()
        for src in ("cam_a", "cam_b"):
            w.update_source(src, np.dtype("uint8"), (2, 2))
            w.prepare(src)
        w.kickoff()
        # first complete should not finalize
        w.complete("cam_a")
        assert w.is_open
        # second complete should finalize
        w.complete("cam_b")
        assert not w.is_open
        assert w._finalized

    def test_clear_source(self) -> None:
        w = self._make_writer()
        w.update_source("cam", np.dtype("uint8"), (2, 2))
        w.clear_source("cam")
        assert "cam" not in w.sources

    def test_clear_missing_source_silent(self) -> None:
        w = self._make_writer()
        w.clear_source("nonexistent")  # should not raise

    def test_clear_missing_source_raises_if_requested(self) -> None:
        w = self._make_writer()
        with pytest.raises(KeyError):
            w.clear_source("nonexistent", raise_if_missing=True)

    def test_get_indices_written_min_across_sources(self) -> None:
        w = self._make_writer()
        for src in ("a", "b"):
            w.update_source(src, np.dtype("uint8"), (2, 2))
            w.prepare(src)
        w.kickoff()
        frame = np.zeros((2, 2), dtype="uint8")
        w._sinks["a"].write(frame) if hasattr(w, "_sinks") else None
        w._sources["a"].frames_written = 1
        # b has 0 frames — min should be 0
        assert w.get_indices_written() == 0

    def test_collect_stream_docs_emits_resource_then_datum(self) -> None:
        w = self._make_writer()
        w.update_source("cam", np.dtype("uint8"), (2, 2))
        w.prepare("cam")
        w.kickoff()
        # Simulate frames written
        w._sources["cam"].frames_written = 3
        docs = list(w.collect_stream_docs("cam", 3))
        kinds = [d[0] for d in docs]
        assert "stream_resource" in kinds
        assert "stream_datum" in kinds

    def test_collect_stream_docs_no_duplicate_resource(self) -> None:
        w = self._make_writer()
        w.update_source("cam", np.dtype("uint8"), (2, 2))
        w.prepare("cam")
        w.kickoff()
        w._sources["cam"].frames_written = 2
        # First call — should include stream_resource
        docs1 = list(w.collect_stream_docs("cam", 2))
        assert any(d[0] == "stream_resource" for d in docs1)
        # Update frames and call again — must NOT emit stream_resource again
        w._sources["cam"].frames_written = 4
        docs2 = list(w.collect_stream_docs("cam", 4))
        assert not any(d[0] == "stream_resource" for d in docs2)


# ---------------------------------------------------------------------------
# StorageProxy structural check
# ---------------------------------------------------------------------------


class TestStorageProxyProtocol:
    def test_writer_satisfies_proxy(self) -> None:
        """Writer must structurally satisfy StorageProxy."""
        assert issubclass(_ConcreteWriter, StorageProxy)


class TestZarrWriterImportGuard:
    def test_import_error_without_acquire_zarr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ZarrWriter.__init__ must raise ImportError when acquire-zarr is absent."""
        import redsun.storage._zarr as zarr_mod
        from redsun.storage._zarr import ZarrWriter

        monkeypatch.setattr(zarr_mod, "_ACQUIRE_ZARR_AVAILABLE", False)
        fp = StaticFilenameProvider("scan")
        pp = StaticPathProvider(fp, base_uri="file:///data")
        with pytest.raises(ImportError, match="acquire-zarr"):
            ZarrWriter("test", pp, Path("/data"))


class TestZarrWriterBaseDir:
    """Tests for ZarrWriter base_dir creation at kickoff."""

    def test_kickoff_creates_base_dir(self, tmp_path: Path) -> None:
        """kickoff() creates base_dir if it does not exist yet."""
        from unittest.mock import MagicMock, patch
        from redsun.storage._zarr import ZarrWriter
        from redsun.storage import StaticFilenameProvider, StaticPathProvider

        base_dir = tmp_path / "scans"
        assert not base_dir.exists()

        fp = StaticFilenameProvider("run001")
        pp = StaticPathProvider(fp, base_uri=base_dir.as_uri())
        writer = ZarrWriter("test-writer", pp, base_dir)

        writer.update_source("cam", dtype=np.dtype("uint16"), shape=(64, 64))

        with patch("redsun.storage._zarr.ZarrStream"):
            writer.prepare("cam", capacity=10)
            writer.kickoff()

        assert base_dir.exists()
        assert base_dir.is_dir()

    def test_kickoff_base_dir_already_exists(self, tmp_path: Path) -> None:
        """kickoff() is a no-op mkdir when base_dir already exists."""
        from unittest.mock import patch
        from redsun.storage._zarr import ZarrWriter
        from redsun.storage import StaticFilenameProvider, StaticPathProvider

        base_dir = tmp_path / "scans"
        base_dir.mkdir()

        fp = StaticFilenameProvider("run001")
        pp = StaticPathProvider(fp, base_uri=base_dir.as_uri())
        writer = ZarrWriter("test-writer", pp, base_dir)

        writer.update_source("cam", dtype=np.dtype("uint16"), shape=(64, 64))

        with patch("redsun.storage._zarr.ZarrStream"):
            writer.prepare("cam", capacity=10)
            writer.kickoff()  # must not raise

        assert base_dir.exists()
