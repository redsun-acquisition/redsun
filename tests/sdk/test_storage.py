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
    DeviceStorageInfo,
    FrameSink,
    HasStorage,
    PathInfo,
    PrepareInfo,
    SessionPathProvider,
    StorageInfo,
    Writer,
    make_writer,
)
from redsun.storage.zarr import ZarrWriter


@pytest.fixture
def current_date() -> str:
    return datetime.datetime.now().strftime("%Y_%m_%d")


class _ConcreteWriter(Writer):
    """Minimal Writer subclass for testing the abstract base."""

    def __init__(self, uri: str) -> None:
        super().__init__(uri)
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


class TestSessionPathProvider:
    def test_uri_structure(self, current_date: str, tmp_path: Path) -> None:
        """URI follows <base_dir>/<session>/<date>/<key>_<counter> format."""
        p = SessionPathProvider(base_dir=tmp_path, session="exp1")
        info = p("live_stream")
        assert info.store_uri == f"file://{tmp_path.as_posix()}/exp1/{current_date}/live_stream_00000"

    def test_counter_increments_per_key(self, tmp_path: Path) -> None:
        """Each call with the same key advances that key's counter."""
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        assert p("snap").store_uri.endswith("snap_00000")
        assert p("snap").store_uri.endswith("snap_00001")
        assert p("snap").store_uri.endswith("snap_00002")

    def test_counters_are_independent_per_key(self, tmp_path: Path) -> None:
        """Different keys have independent counters."""
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        p("live_stream")
        p("live_stream")
        assert p("snap").store_uri.endswith("snap_00000")
        assert p("live_stream").store_uri.endswith("live_stream_00002")

    def test_none_key_maps_to_default(self, tmp_path: Path) -> None:
        """key=None uses 'default' as the bucket name."""
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        info = p(None)
        assert "default_00000" in info.store_uri
        assert info.array_key == "default"

    def test_array_key_matches_key(self, tmp_path: Path) -> None:
        """PathInfo.array_key is set to the resolved key."""
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        info = p("camera")
        assert info.array_key == "camera"

    def test_overflow_raises(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s", max_digits=1)
        for _ in range(9):
            p("x")
        p("x")  # 9 → ok (single digit)
        with pytest.raises(ValueError, match="exceeded maximum"):
            p("x")  # 10 → two digits

    def test_capacity_forwarded(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s", capacity=100)
        assert p("x").capacity == 100

    def test_default_base_dir_is_home(self) -> None:
        """Default base_dir is ~/redsun-storage."""
        p = SessionPathProvider(session="s")
        expected = Path.home() / "redsun-storage"
        assert p.base_dir == expected

    def test_scan_existing_on_construction(self, current_date: str, tmp_path: Path) -> None:
        """Counters are initialised from existing directories on construction."""
        date_dir = tmp_path / "s" / current_date
        date_dir.mkdir(parents=True)
        (date_dir / "snap_00000").mkdir()
        (date_dir / "snap_00001").mkdir()
        (date_dir / "snap_00002").mkdir()
        (date_dir / "live_stream_00000").mkdir()
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        assert p("snap").store_uri.endswith("snap_00003")
        assert p("live_stream").store_uri.endswith("live_stream_00001")

    def test_scan_ignores_files(self, current_date: str, tmp_path: Path) -> None:
        """Plain files in the date directory are not counted."""
        date_dir = tmp_path / "s" / current_date
        date_dir.mkdir(parents=True)
        (date_dir / "snap_00000").touch()  # file, not dir — must be ignored
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        assert p("snap").store_uri.endswith("snap_00000")

    def test_scan_ignores_unparseable_entries(self, current_date: str, tmp_path: Path) -> None:
        """Directories that don't match <key>_<N> are silently skipped."""
        date_dir = tmp_path / "s" / current_date
        date_dir.mkdir(parents=True)
        (date_dir / "nodigit_abc").mkdir()
        (date_dir / "nodash").mkdir()
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        assert p("nodigit").store_uri.endswith("nodigit_00000")

    def test_missing_date_dir_starts_from_zero(self, tmp_path: Path) -> None:
        """Missing date directory silently starts counters from zero."""
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        assert p("snap").store_uri.endswith("snap_00000")

    def test_session_setter_rescans(self, current_date: str, tmp_path: Path) -> None:
        """Updating session rescans the new session's directory."""
        date_dir = tmp_path / "b" / current_date
        date_dir.mkdir(parents=True)
        (date_dir / "snap_00000").mkdir()
        (date_dir / "snap_00001").mkdir()
        p = SessionPathProvider(base_dir=tmp_path, session="a")
        p("snap")  # a/snap → 00000
        p.session = "b"
        info = p("snap")
        assert "snap_00002" in info.store_uri
        assert "b" in info.store_uri.split("snap")[0]

    def test_base_dir_setter_rescans(self, current_date: str, tmp_path: Path) -> None:
        """Updating base_dir rescans the new location."""
        new_dir = tmp_path / "new"
        date_dir = new_dir / "s" / current_date
        date_dir.mkdir(parents=True)
        (date_dir / "snap_00000").mkdir()
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        p("snap")  # old location → 00000
        p.base_dir = new_dir
        info = p("snap")
        assert "snap_00001" in info.store_uri
        assert new_dir.as_posix() in info.store_uri


class TestWriter:
    def _make_writer(self, uri: str = "file:///tmp/test.zarr") -> _ConcreteWriter:
        return _ConcreteWriter(uri)

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
        with pytest.raises(ImportError, match="acquire-zarr"):
            ZarrWriter("file:///tmp/test.zarr")


class TestZarrWriterKickoff:
    def test_kickoff(self, tmp_path: Path) -> None:
        """kickoff() opens the ZarrStream with the configured store path."""
        uri = tmp_path.as_uri() + "/scan.zarr"
        writer = ZarrWriter(uri)
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
        with pytest.raises(ValueError, match="Unsupported format hint"):
            make_writer("file:///tmp/scan.zarr", "application/x-unknown")

    def test_returns_zarr_writer(self) -> None:
        w = make_writer("file:///tmp/scan.zarr")
        assert isinstance(w, ZarrWriter)

    def test_same_uri_returns_same_instance(self) -> None:
        """Two calls with the same URI must return the same writer."""
        uri = "file:///tmp/singleton_test.zarr"
        w1 = make_writer(uri)
        w2 = make_writer(uri)
        assert w1 is w2

    def test_different_uri_returns_different_instance(self) -> None:
        w1 = make_writer("file:///tmp/a.zarr")
        w2 = make_writer("file:///tmp/b.zarr")
        assert w1 is not w2

    def test_registry_cleared_after_complete(self) -> None:
        """After all sources complete, the next call returns a fresh instance."""
        uri = "file:///tmp/release_test.zarr"
        w1 = _ConcreteWriter.get(uri)
        w1.update_source("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        w1.prepare("cam")
        w1.kickoff()
        w1.complete("cam")  # last source — triggers release
        w2 = _ConcreteWriter.get(uri)
        assert w1 is not w2


class TestPrepareInfo:
    def test_default_constructs_empty_storage_info(self) -> None:
        """PrepareInfo() with no args should produce an empty StorageInfo, not None."""
        pi = PrepareInfo()
        assert isinstance(pi.storage, StorageInfo)
        assert pi.storage.uri == ""
        assert pi.storage.devices == {}

    def test_accepts_explicit_storage_info(self) -> None:
        info = StorageInfo(uri="file:///tmp/scan.zarr")
        pi = PrepareInfo(storage=info)
        assert pi.storage is info

    def test_storage_is_never_none(self) -> None:
        """PrepareInfo.storage is always a StorageInfo — no None sentinel."""
        assert PrepareInfo().storage is not None

    def test_each_default_instance_is_independent(self) -> None:
        """Two PrepareInfo() calls must not share the same StorageInfo instance."""
        pi1 = PrepareInfo()
        pi2 = PrepareInfo()
        pi1.storage.devices["motor"] = DeviceStorageInfo(mimetype="application/x-zarr")
        assert "motor" not in pi2.storage.devices

    def test_accessible_via_getattr_without_import(self) -> None:
        """Third-party code can reach storage via getattr without importing PrepareInfo."""
        pi = PrepareInfo()
        assert getattr(pi, "storage", None) is not None


class TestStorageInfoDefaults:
    def test_no_args_constructor(self) -> None:
        """StorageInfo() is valid with no arguments — uri defaults to empty string."""
        info = StorageInfo()
        assert info.uri == ""
        assert info.devices == {}

    def test_uri_settable_after_construction(self) -> None:
        info = StorageInfo()
        info.uri = "file:///data/scan.zarr"
        assert info.uri == "file:///data/scan.zarr"

    def test_empty_instances_are_independent(self) -> None:
        """Two StorageInfo() calls must not share the same devices dict."""
        a = StorageInfo()
        b = StorageInfo()
        a.devices["cam"] = DeviceStorageInfo(mimetype="application/x-zarr")
        assert "cam" not in b.devices
