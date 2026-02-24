"""Smoke tests for redsun.storage."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
from redsun.storage.zarr import ZarrWriter

from redsun.storage import (
    AutoIncrementFilenameProvider,
    DeviceStorageInfo,
    FrameSink,
    PathInfo,
    StaticPathProvider,
    StorageInfo,
    Writer,
)

from redsun.storage import make_writer
from redsun.storage.zarr import ZarrWriter
from redsun.storage import HasStorage


@pytest.fixture
def current_date() -> str:
    return datetime.datetime.now().strftime("%Y_%m_%d")


@pytest.fixture
def storage_info() -> StorageInfo:
    return StorageInfo(
        uri="file:///tmp/test.zarr",
        devices={"cam": DeviceStorageInfo(mimetype="application/x-zarr")},
    )


class _ConcreteWriter(Writer):
    """Minimal Writer subclass for testing the abstract base."""

    def __init__(self, info: StorageInfo) -> None:
        super().__init__(info)
        self._frames: dict[str, list[Any]] = {}
        self._finalized = False

    @property
    def mimetype(self) -> str:
        return "application/x-test"

    def prepare(self, name: str, capacity: int = 0) -> FrameSink:
        self._frames.setdefault(name, [])
        return super().prepare(name, capacity)

    def kickoff(self) -> None:
        super().kickoff()

    def _write_frame(self, name: str, frame: Any) -> None:
        self._frames[name].append(frame)

    def _finalize(self) -> None:
        self._finalized = True


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

    def test_scan_empty_dir(self, tmp_path: Path, current_date: str) -> None:
        """Empty directory should start from 0."""
        p = AutoIncrementFilenameProvider(base="scan", max_digits=5, base_dir=tmp_path, suffix=".zarr")
        assert p() == "_".join([current_date, "scan_00000"]) + ".zarr"

    def test_scan_picks_up_existing(self, tmp_path: Path, current_date: str) -> None:
        """Counter should start one past the highest existing entry."""
        (tmp_path / f"{current_date}_scan_00000.zarr").mkdir()
        (tmp_path / f"{current_date}_scan_00001.zarr").mkdir()
        (tmp_path / f"{current_date}_scan_00002.zarr").mkdir()
        p = AutoIncrementFilenameProvider(base="scan", max_digits=5, base_dir=tmp_path, suffix=".zarr")
        assert p() == "_".join([current_date, "scan_00003"]) + ".zarr"

    def test_scan_picks_up_across_dates(self, tmp_path: Path, current_date: str) -> None:
        """Counter should account for entries from previous days."""
        (tmp_path / "2024_01_01_scan_00007.zarr").mkdir()
        p = AutoIncrementFilenameProvider(base="scan", max_digits=5, base_dir=tmp_path, suffix=".zarr")
        assert p() == "_".join([current_date, "scan_00008"]) + ".zarr"

    def test_scan_ignores_unrelated_files(self, tmp_path: Path, current_date: str) -> None:
        """Files that don't match the pattern should not affect the counter."""
        (tmp_path / "some_other_file.zarr").touch()
        (tmp_path / "background.zarr").mkdir()
        p = AutoIncrementFilenameProvider(base="scan", max_digits=5, base_dir=tmp_path, suffix=".zarr")
        assert p() == "_".join([current_date, "scan_00000"]) + ".zarr"

    def test_scan_nonexistent_dir_starts_from_zero(self, tmp_path: Path, current_date: str) -> None:
        """A base_dir that doesn't exist yet should not raise and should start from 0."""
        p = AutoIncrementFilenameProvider(
            base="scan", max_digits=5, base_dir=tmp_path / "new_session", suffix=".zarr"
        )
        assert p() == "_".join([current_date, "scan_00000"]) + ".zarr"


class TestStaticPathProvider:
    def test_basic(self, current_date: str) -> None:
        fp = AutoIncrementFilenameProvider(base="scan", max_digits=5, start=0)
        pp = StaticPathProvider(fp, base_uri="file:///data")
        info = pp("camera")
        assert info.store_uri == "file:///data/" + "_".join([current_date, "scan_00000"])
        assert info.array_key == "camera"

    def test_trailing_slash_stripped(self, current_date: str) -> None:
        fp = AutoIncrementFilenameProvider(base="scan", max_digits=5, start=0)
        pp = StaticPathProvider(fp, base_uri="file:///data/")
        info = pp("det")
        assert info.store_uri == "file:///data/" + "_".join([current_date, "scan_00000"])

    def test_none_device_name(self, current_date: str) -> None:
        fp = AutoIncrementFilenameProvider(base="scan", max_digits=5, start=0)
        pp = StaticPathProvider(fp, base_uri="file:///data")
        info = pp(None)
        assert info.array_key == "_".join([current_date, "scan_00000"])

    def test_capacity_forwarded(self) -> None:
        fp = AutoIncrementFilenameProvider(base="scan", max_digits=5, start=0)
        pp = StaticPathProvider(fp, base_uri="file:///d", capacity=50)
        assert pp("x").capacity == 50


class TestWriter:
    def _make_writer(self, info: StorageInfo | None = None) -> _ConcreteWriter:
        if info is None:
            info = StorageInfo(uri="file:///tmp/test.zarr")
        return _ConcreteWriter(info)

    def test_initial_state(self) -> None:
        w = self._make_writer()
        assert not w.is_open
        assert w.uri == "file:///tmp/test.zarr"
        assert len(w._sources) == 0

    def test_update_source(self) -> None:
        w = self._make_writer()
        w.update_source("cam", "cam-buffer_stream", np.dtype("uint8"), (512, 512))
        assert "cam" in w._sources
        assert w._sources["cam"].shape == (512, 512)

    def test_update_source_while_open_raises(self) -> None:
        w = self._make_writer()
        w.update_source("cam", "cam-buffer_stream", np.dtype("uint8"), (64, 64))
        w.prepare("cam")
        w.kickoff()
        with pytest.raises(RuntimeError, match="open"):
            w.update_source("cam2", "cam2-buffer_stream", np.dtype("uint8"), (64, 64))

    def test_prepare_returns_sink(self) -> None:
        w = self._make_writer()
        w.update_source("cam", "cam-buffer_stream", np.dtype("uint8"), (4, 4))
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
        w.update_source("cam", "cam-buffer_stream", np.dtype("uint8"), (4, 4))
        w.prepare("cam")
        w.kickoff()
        assert w.is_open

    def test_frame_written_via_sink(self) -> None:
        w = self._make_writer()
        w.update_source("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        sink = w.prepare("cam")
        w.kickoff()
        frame = np.zeros((2, 2), dtype="uint8")
        sink.write(frame)
        assert w.get_indices_written("cam") == 1
        assert w._frames["cam"][0] is frame

    def test_complete_finalizes(self) -> None:
        w = self._make_writer()
        w.update_source("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        w.prepare("cam")
        w.kickoff()
        w.complete("cam")
        assert not w.is_open
        assert w._finalized

    def test_clear_source(self) -> None:
        w = self._make_writer()
        w.update_source("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        w.clear_source("cam")
        assert "cam" not in w._sources

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
            w.update_source(src, f"{src}-buffer_stream", np.dtype("uint8"), (2, 2))
            w.prepare(src)
        w.kickoff()
        w._sources["a"].frames_written = 1
        assert w.get_indices_written() == 0

    def test_collect_stream_docs_emits_resource_then_datum(self) -> None:
        w = self._make_writer()
        w.update_source("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        w.prepare("cam")
        w.kickoff()
        w._sources["cam"].frames_written = 3
        docs = list(w.collect_stream_docs("cam", 3))
        kinds = [d[0] for d in docs]
        assert "stream_resource" in kinds
        assert "stream_datum" in kinds

    def test_collect_stream_docs_mimetype_from_writer(self) -> None:
        """stream_resource mimetype must come from Writer.mimetype, not SourceInfo."""
        w = self._make_writer()
        w.update_source("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        w.prepare("cam")
        w.kickoff()
        w._sources["cam"].frames_written = 1
        docs = list(w.collect_stream_docs("cam", 1))
        resource = next(d for kind, d in docs if kind == "stream_resource")
        assert resource["mimetype"] == "application/x-test"

    def test_collect_stream_docs_no_duplicate_resource(self) -> None:
        w = self._make_writer()
        w.update_source("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        w.prepare("cam")
        w.kickoff()
        w._sources["cam"].frames_written = 2
        docs1 = list(w.collect_stream_docs("cam", 2))
        assert any(d[0] == "stream_resource" for d in docs1)
        w._sources["cam"].frames_written = 4
        docs2 = list(w.collect_stream_docs("cam", 4))
        assert not any(d[0] == "stream_resource" for d in docs2)


class TestZarrWriterImportGuard:
    def test_import_error_without_acquire_zarr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ZarrWriter.__init__ must raise ImportError when acquire-zarr is absent."""
        import redsun.storage.zarr as zarr_mod

        monkeypatch.setattr(zarr_mod, "_ACQUIRE_ZARR_AVAILABLE", False)
        info = StorageInfo(
            uri="file:///tmp/test.zarr",
            devices={"cam": DeviceStorageInfo(mimetype="application/x-zarr")},
        )
        with pytest.raises(ImportError, match="acquire-zarr"):
            ZarrWriter(info)


class TestZarrWriterKickoff:
    def test_kickoff(self, tmp_path: Path) -> None:
        """kickoff() opens the ZarrStream with the configured store path."""
        info = StorageInfo(
            uri=tmp_path.as_uri() + "/scan.zarr",
            devices={"cam": DeviceStorageInfo(mimetype="application/x-zarr")},
        )
        writer = ZarrWriter(info)
        writer.update_source("cam", "cam-buffer_stream", dtype=np.dtype("uint16"), shape=(64, 64))

        with patch("redsun.storage.zarr.ZarrStream"):
            writer.prepare("cam", capacity=10)
            writer.kickoff()

        assert writer.is_open


class TestDeviceStorageInfo:
    def test_defaults(self) -> None:
        info = DeviceStorageInfo(mimetype="application/x-zarr")
        assert info.mimetype == "application/x-zarr"
        assert info.extra == {}

    def test_extra_is_mutable(self) -> None:
        info = DeviceStorageInfo(mimetype="application/x-zarr")
        info.extra["key"] = "value"
        assert info.extra["key"] == "value"

    def test_no_uri_field(self) -> None:
        info = DeviceStorageInfo(mimetype="application/x-zarr")
        assert not hasattr(info, "uri")


class TestStorageInfo:
    def test_defaults(self) -> None:
        info = StorageInfo(uri="file:///tmp/scan.zarr")
        assert info.uri == "file:///tmp/scan.zarr"
        assert info.devices == {}

    def test_devices_is_mutable_and_shared(self) -> None:
        """Mutations on devices dict are visible to all references to the same instance."""
        info = StorageInfo(uri="file:///tmp/scan.zarr")
        ref = info
        info.devices["motor"] = DeviceStorageInfo(mimetype="application/x-zarr")
        assert "motor" in ref.devices

    def test_two_devices_do_not_overwrite(self) -> None:
        info = StorageInfo(uri="file:///tmp/scan.zarr")
        info.devices["cam"] = DeviceStorageInfo(mimetype="application/x-zarr", extra={"x": 1})
        info.devices["motor"] = DeviceStorageInfo(mimetype="application/x-zarr", extra={"y": 2})
        assert info.devices["cam"].extra == {"x": 1}
        assert info.devices["motor"].extra == {"y": 2}


class TestHasStorageProtocol:
    def test_isinstance_passes_for_compliant_class(self) -> None:

        class _FakeDevice:
            @property
            def name(self) -> str:
                return "dev"

            def storage_info(self) -> DeviceStorageInfo:
                return DeviceStorageInfo(mimetype="application/x-zarr")

        assert isinstance(_FakeDevice(), HasStorage)

    def test_isinstance_fails_without_storage_info(self) -> None:

        class _NoStorage:
            @property
            def name(self) -> str:
                return "dev"

        assert not isinstance(_NoStorage(), HasStorage)

    def test_isinstance_fails_without_name(self) -> None:

        class _NoName:
            def storage_info(self) -> DeviceStorageInfo:
                return DeviceStorageInfo(mimetype="application/x-zarr")

        assert not isinstance(_NoName(), HasStorage)


class TestMakeWriter:
    def test_raises_for_unknown_format(self) -> None:
        info = StorageInfo(
            uri="file:///tmp/scan.zarr",
            devices={"cam": DeviceStorageInfo(mimetype="application/x-unknown")},
        )
        with pytest.raises(ValueError, match="Unsupported format hint"):
            make_writer("cam", info)

    def test_returns_zarr_writer(self) -> None:
        info = StorageInfo(
            uri="file:///tmp/scan.zarr",
            devices={"cam": DeviceStorageInfo(mimetype="application/x-zarr")},
        )
        w = make_writer("cam", info)
        assert isinstance(w, ZarrWriter)

    def test_unknown_device_falls_back_to_zarr(self) -> None:
        """make_writer with a name not in info.devices defaults to zarr."""

        info = StorageInfo(uri="file:///tmp/scan.zarr")
        w = make_writer("unknown_device", info)
        assert isinstance(w, ZarrWriter)
