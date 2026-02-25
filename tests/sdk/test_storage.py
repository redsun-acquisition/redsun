"""Smoke tests for redsun.storage."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

from redsun.storage import (
    PathInfo,
    PrepareInfo,
    SessionPathProvider,
)
from redsun.storage._base import FrameSink, Writer
from redsun.storage._zarr import ZarrWriter
from redsun.storage.device import make_writer


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear the Writer registry before and after each test."""
    Writer._registry.clear()
    yield
    Writer._registry.clear()


@pytest.fixture
def current_date() -> str:
    return datetime.datetime.now().strftime("%Y_%m_%d")


class _ConcreteWriter(Writer):
    """Minimal Writer subclass for testing the abstract base."""

    def __init__(self, name: str = "default") -> None:
        super().__init__(name)
        self._frames: dict[str, list[Any]] = {}
        self._finalized = False

    @classmethod
    def _class_mimetype(cls) -> str:
        return "application/x-test"

    def _on_prepare(self, name: str) -> None:
        self._frames.setdefault(name, [])

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
        p = SessionPathProvider(base_dir=tmp_path, session="exp1")
        info = p("live_stream")
        assert info.store_uri == f"file://{tmp_path.as_posix()}/exp1/{current_date}/live_stream_00000"

    def test_counter_increments_per_key(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        assert p("snap").store_uri.endswith("snap_00000")
        assert p("snap").store_uri.endswith("snap_00001")
        assert p("snap").store_uri.endswith("snap_00002")

    def test_counters_are_independent_per_key(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        p("live_stream")
        p("live_stream")
        assert p("snap").store_uri.endswith("snap_00000")
        assert p("live_stream").store_uri.endswith("live_stream_00002")

    def test_none_key_maps_to_default(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        info = p(None)
        assert "default_00000" in info.store_uri
        assert info.array_key == "default"

    def test_array_key_matches_key(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        info = p("camera")
        assert info.array_key == "camera"

    def test_overflow_raises(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s", max_digits=1)
        for _ in range(9):
            p("x")
        p("x")
        with pytest.raises(ValueError, match="exceeded maximum"):
            p("x")

    def test_capacity_forwarded(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s", capacity=100)
        assert p("x").capacity == 100

    def test_default_base_dir_is_home(self) -> None:
        p = SessionPathProvider(session="s")
        expected = Path.home() / "redsun-storage"
        assert p.base_dir == expected

    def test_scan_existing_on_construction(self, current_date: str, tmp_path: Path) -> None:
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
        date_dir = tmp_path / "s" / current_date
        date_dir.mkdir(parents=True)
        (date_dir / "snap_00000").touch()
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        assert p("snap").store_uri.endswith("snap_00000")

    def test_scan_ignores_unparseable_entries(self, current_date: str, tmp_path: Path) -> None:
        date_dir = tmp_path / "s" / current_date
        date_dir.mkdir(parents=True)
        (date_dir / "nodigit_abc").mkdir()
        (date_dir / "nodash").mkdir()
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        assert p("nodigit").store_uri.endswith("nodigit_00000")

    def test_missing_date_dir_starts_from_zero(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        assert p("snap").store_uri.endswith("snap_00000")

    def test_session_setter_rescans(self, current_date: str, tmp_path: Path) -> None:
        date_dir = tmp_path / "b" / current_date
        date_dir.mkdir(parents=True)
        (date_dir / "snap_00000").mkdir()
        (date_dir / "snap_00001").mkdir()
        p = SessionPathProvider(base_dir=tmp_path, session="a")
        p("snap")
        p.session = "b"
        info = p("snap")
        assert "snap_00002" in info.store_uri
        assert "b" in info.store_uri.split("snap")[0]

    def test_base_dir_setter_rescans(self, current_date: str, tmp_path: Path) -> None:
        new_dir = tmp_path / "new"
        date_dir = new_dir / "s" / current_date
        date_dir.mkdir(parents=True)
        (date_dir / "snap_00000").mkdir()
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        p("snap")
        p.base_dir = new_dir
        info = p("snap")
        assert "snap_00001" in info.store_uri
        assert new_dir.as_posix() in info.store_uri


class TestWriter:
    def _make_writer(self, name: str = "default") -> _ConcreteWriter:
        return _ConcreteWriter(name)

    def test_initial_state(self) -> None:
        w = self._make_writer()
        assert not w.is_open
        assert w.uri == ""
        assert len(w._sources) == 0

    def test_set_uri(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        assert w.uri == "file:///tmp/test.zarr"

    def test_set_uri_while_open_raises(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (4, 4))
        w.kickoff()
        with pytest.raises(RuntimeError, match="open"):
            w.set_uri("file:///tmp/other.zarr")

    def test_prepare_returns_sink(self) -> None:
        w = self._make_writer()
        sink = w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (4, 4))
        assert isinstance(sink, FrameSink)
        assert hasattr(sink, "write")
        assert hasattr(sink, "close")

    def test_prepare_registers_source(self) -> None:
        w = self._make_writer()
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (512, 512))
        assert "cam" in w._sources
        assert w._sources["cam"].shape == (512, 512)

    def test_prepare_while_open_raises(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (4, 4))
        w.kickoff()
        with pytest.raises(RuntimeError, match="open"):
            w.prepare("cam2", "cam2-buffer_stream", np.dtype("uint8"), (4, 4))

    def test_prepare_resets_counters_on_repeat(self) -> None:
        w = self._make_writer()
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (4, 4))
        w._sources["cam"].frames_written = 5
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (4, 4))
        assert w._sources["cam"].frames_written == 0

    def test_kickoff_sets_open(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (4, 4))
        w.kickoff()
        assert w.is_open

    def test_kickoff_without_uri_raises(self) -> None:
        w = self._make_writer()
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (4, 4))
        with pytest.raises(RuntimeError, match="no URI"):
            w.kickoff()

    def test_frame_written_via_sink(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        sink = w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        w.kickoff()
        frame = np.zeros((2, 2), dtype="uint8")
        sink.write(frame)
        assert w.get_indices_written("cam") == 1
        assert w._frames["cam"][0] is frame

    def test_complete_finalizes_when_last_source(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        w.kickoff()
        w.complete("cam")
        assert not w.is_open
        assert w._finalized

    def test_complete_does_not_release_from_registry(self) -> None:
        """Writer stays in registry after completion — it is long-lived."""
        w = _ConcreteWriter.get("default")
        w.set_uri("file:///tmp/test.zarr")
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        w.kickoff()
        w.complete("cam")
        key = ("default", "application/x-test")
        assert key in Writer._registry
        assert Writer._registry[key] is w

    def test_complete_with_multiple_sources_only_finalizes_on_last(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.prepare("a", "a-stream", np.dtype("uint8"), (2, 2))
        w.prepare("b", "b-stream", np.dtype("uint8"), (2, 2))
        w.kickoff()
        w.complete("a")
        assert w.is_open
        assert not w._finalized
        w.complete("b")
        assert not w.is_open
        assert w._finalized

    def test_clear_source(self) -> None:
        w = self._make_writer()
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        w.clear_source("cam")
        assert "cam" not in w._sources

    def test_clear_missing_source_silent(self) -> None:
        w = self._make_writer()
        w.clear_source("nonexistent")

    def test_clear_missing_source_raises_if_requested(self) -> None:
        w = self._make_writer()
        with pytest.raises(KeyError):
            w.clear_source("nonexistent", raise_if_missing=True)

    def test_get_indices_written_min_across_sources(self) -> None:
        w = self._make_writer()
        w.prepare("a", "a-stream", np.dtype("uint8"), (2, 2))
        w.prepare("b", "b-stream", np.dtype("uint8"), (2, 2))
        w.set_uri("file:///tmp/test.zarr")
        w.kickoff()
        w._sources["a"].frames_written = 1
        assert w.get_indices_written() == 0

    def test_update_metadata_stores_dict(self) -> None:
        w = self._make_writer()
        w.update_metadata("motor", {"position": 1.5, "units": "mm"})
        assert w._metadata["motor"] == {"position": 1.5, "units": "mm"}

    def test_update_metadata_while_open_raises(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (4, 4))
        w.kickoff()
        with pytest.raises(RuntimeError, match="open"):
            w.update_metadata("motor", {"position": 1.5})

    def test_collect_stream_docs_emits_resource_then_datum(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        w.kickoff()
        w._sources["cam"].frames_written = 3
        docs = list(w.collect_stream_docs("cam", 3))
        kinds = [d[0] for d in docs]
        assert "stream_resource" in kinds
        assert "stream_datum" in kinds

    def test_collect_stream_docs_mimetype_from_writer(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        w.kickoff()
        w._sources["cam"].frames_written = 1
        docs = list(w.collect_stream_docs("cam", 1))
        resource = next(d for kind, d in docs if kind == "stream_resource")
        assert resource["mimetype"] == "application/x-test"

    def test_collect_stream_docs_no_duplicate_resource(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.prepare("cam", "cam-buffer_stream", np.dtype("uint8"), (2, 2))
        w.kickoff()
        w._sources["cam"].frames_written = 2
        docs1 = list(w.collect_stream_docs("cam", 2))
        assert any(d[0] == "stream_resource" for d in docs1)
        w._sources["cam"].frames_written = 4
        docs2 = list(w.collect_stream_docs("cam", 4))
        assert not any(d[0] == "stream_resource" for d in docs2)


class TestWriterRegistry:
    def test_get_returns_same_instance(self) -> None:
        w1 = _ConcreteWriter.get("default")
        w2 = _ConcreteWriter.get("default")
        assert w1 is w2

    def test_different_names_return_different_instances(self) -> None:
        w1 = _ConcreteWriter.get("default")
        w2 = _ConcreteWriter.get("live")
        assert w1 is not w2

    def test_registry_key_is_name_and_mimetype(self) -> None:
        _ConcreteWriter.get("default")
        assert ("default", "application/x-test") in Writer._registry

    def test_release_removes_from_registry(self) -> None:
        _ConcreteWriter.get("default")
        _ConcreteWriter.release("default")
        assert ("default", "application/x-test") not in Writer._registry

    def test_get_after_release_returns_fresh_instance(self) -> None:
        w1 = _ConcreteWriter.get("default")
        _ConcreteWriter.release("default")
        w2 = _ConcreteWriter.get("default")
        assert w1 is not w2

    def test_wrong_subclass_raises_type_error(self) -> None:
        """Registering one subclass and fetching with another raises TypeError."""
        _ConcreteWriter.get("default")

        class _OtherWriter(_ConcreteWriter):
            @classmethod
            def _class_mimetype(cls) -> str:
                return "application/x-test"

        with pytest.raises(TypeError):
            _OtherWriter.get("default")


class TestPrepareInfo:
    def test_defaults(self) -> None:
        pi = PrepareInfo()
        assert pi.capacity == 0
        assert pi.write_forever is False

    def test_custom_values(self) -> None:
        pi = PrepareInfo(capacity=100, write_forever=True)
        assert pi.capacity == 100
        assert pi.write_forever is True

    def test_instances_are_independent(self) -> None:
        pi1 = PrepareInfo(capacity=10)
        pi2 = PrepareInfo(capacity=20)
        assert pi1.capacity != pi2.capacity


class TestZarrWriterImportGuard:
    def test_import_error_without_acquire_zarr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import redsun.storage._zarr as zarr_mod
        monkeypatch.setattr(zarr_mod, "_ACQUIRE_ZARR_AVAILABLE", False)
        with pytest.raises(ImportError, match="acquire-zarr"):
            ZarrWriter("default")


class TestZarrWriterKickoff:
    def test_kickoff(self, tmp_path: Path) -> None:
        uri = tmp_path.as_uri() + "/scan.zarr"
        writer = ZarrWriter.get("default")
        writer.set_uri(uri)
        writer.prepare(
            "cam",
            "cam-buffer_stream",
            dtype=np.dtype("uint16"),
            shape=(64, 64),
            capacity=10,
        )
        with patch("redsun.storage._zarr.ZarrStream"):
            writer.kickoff()
        assert writer.is_open

    def test_set_uri_updates_store_path(self, tmp_path: Path) -> None:
        uri = tmp_path.as_uri() + "/scan.zarr"
        writer = ZarrWriter.get("default")
        writer.set_uri(uri)
        from redsun.storage.utils import from_uri
        assert writer._stream_settings.store_path == from_uri(uri)

    def test_metadata_written_on_kickoff(self, tmp_path: Path) -> None:
        uri = tmp_path.as_uri() + "/scan.zarr"
        writer = ZarrWriter.get("default")
        writer.set_uri(uri)
        writer.prepare("cam", "cam-buffer_stream", dtype=np.dtype("uint16"), shape=(64, 64))
        writer.update_metadata("motor", {"position": 1.5})
        with patch("redsun.storage._zarr.ZarrStream") as mock_stream_cls:
            writer.kickoff()
            mock_stream_cls.return_value.write_custom_metadata.assert_called_once()


class TestMakeWriter:
    def test_raises_for_unknown_mimetype(self) -> None:
        with pytest.raises(ValueError, match="Unsupported mimetype"):
            make_writer("application/x-unknown")

    def test_returns_zarr_writer(self) -> None:
        w = make_writer("application/x-zarr")
        assert isinstance(w, ZarrWriter)

    def test_same_name_returns_same_instance(self) -> None:
        w1 = make_writer("application/x-zarr", name="default")
        w2 = make_writer("application/x-zarr", name="default")
        assert w1 is w2

    def test_different_names_return_different_instances(self) -> None:
        w1 = make_writer("application/x-zarr", name="default")
        w2 = make_writer("application/x-zarr", name="live")
        assert w1 is not w2
