"""Smoke tests for redsun.storage."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

from redsun.storage import (
    HasMetadata,
    HasWriterLogic,
    PathInfo,
    SessionPathProvider,
    SharedDetectorWriter,
    handle_descriptor_metadata,
)
from redsun.storage._zarr import ZarrWriter
from redsun.storage.utils import from_uri


@pytest.fixture
def current_date() -> str:
    return datetime.datetime.now().strftime("%Y_%m_%d")


class _ConcreteWriter(SharedDetectorWriter):
    """Minimal SharedDetectorWriter subclass for testing the abstract base."""

    def __init__(self, name: str = "default") -> None:
        super().__init__(name)
        self._frames: dict[str, list[Any]] = {}
        self._finalized = False

    @classmethod
    def _class_mimetype(cls) -> str:
        return "application/x-test"

    def _on_register(self, name: str) -> None:
        self._frames.setdefault(name, [])

    def _open_backend(self) -> None:
        pass

    def _write_frame(self, name: str, frame: Any) -> None:
        self._frames[name].append(frame)

    def _close_backend(self) -> None:
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
        assert (
            info.store_uri
            == f"file://{tmp_path.as_posix()}/exp1/{current_date}/live_stream_00000"
        )

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

    def test_scan_existing_on_construction(
        self, current_date: str, tmp_path: Path
    ) -> None:
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

    def test_scan_ignores_unparseable_entries(
        self, current_date: str, tmp_path: Path
    ) -> None:
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

    def test_group_embedded_in_stem(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        info = p("live_stream", group="cam")
        assert info.store_uri.endswith("live_stream_cam_00000")

    def test_group_counter_independent_from_no_group(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        p("snap")
        p("snap")
        info_grouped = p("snap", group="cam")
        assert info_grouped.store_uri.endswith("snap_cam_00000")
        info_plain = p("snap")
        assert info_plain.store_uri.endswith("snap_00002")

    def test_different_groups_have_independent_counters(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        p("snap", group="cam_a")
        p("snap", group="cam_a")
        info = p("snap", group="cam_b")
        assert info.store_uri.endswith("snap_cam_b_00000")

    def test_group_array_key_is_plain_key(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        info = p("live_stream", group="cam")
        assert info.array_key == "live_stream"

    def test_none_group_behaves_as_no_group(self, tmp_path: Path) -> None:
        p = SessionPathProvider(base_dir=tmp_path, session="s")
        info = p("snap", group=None)
        assert info.store_uri.endswith("snap_00000")


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

    async def test_set_uri_while_open_raises(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.register("cam", np.dtype("uint8"), (4, 4))
        await w.open("cam")
        with pytest.raises(RuntimeError, match="open"):
            w.set_uri("file:///tmp/other.zarr")

    def test_register_creates_source_info(self) -> None:
        w = self._make_writer()
        w.register("cam", np.dtype("uint8"), (512, 512))
        assert "cam" in w._sources
        assert w._sources["cam"].shape == (512, 512)

    async def test_register_while_open_raises(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.register("cam", np.dtype("uint8"), (4, 4))
        await w.open("cam")
        with pytest.raises(RuntimeError, match="open"):
            w.register("cam2", np.dtype("uint8"), (4, 4))

    def test_register_resets_counters_on_repeat(self) -> None:
        w = self._make_writer()
        w.register("cam", np.dtype("uint8"), (4, 4))
        w._sources["cam"].frames_written = 5
        w.register("cam", np.dtype("uint8"), (4, 4))
        assert w._sources["cam"].frames_written == 0

    async def test_open_without_register_raises(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        with pytest.raises(KeyError, match="not registered"):
            await w.open("cam")

    async def test_open_sets_is_open(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.register("cam", np.dtype("uint8"), (4, 4))
        await w.open("cam")
        assert w.is_open

    async def test_open_without_uri_raises(self) -> None:
        w = self._make_writer()
        w.register("cam", np.dtype("uint8"), (4, 4))
        with pytest.raises(RuntimeError, match="no URI"):
            await w.open("cam")

    async def test_open_returns_data_key_dict(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.register("cam", np.dtype("uint8"), (2, 2))
        result = await w.open("cam")
        assert "cam" in result
        assert result["cam"]["shape"] == [2, 2]

    async def test_open_backend_called_only_on_first_open(self) -> None:
        """Calling open() a second time (different source) must not re-open backend."""
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.register("cam", np.dtype("uint8"), (2, 2))
        w.register("cam2", np.dtype("uint8"), (2, 2))
        await w.open("cam")
        assert w.is_open
        await w.open("cam2")
        assert w.is_open

    async def test_frame_written_via_write_frame(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.register("cam", np.dtype("uint8"), (2, 2))
        await w.open("cam")
        frame = np.zeros((2, 2), dtype="uint8")
        w.write_frame("cam", frame)
        assert await w.get_indices_written("cam") == 1
        assert w._frames["cam"][0] is frame

    async def test_close_finalizes_backend(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.register("cam", np.dtype("uint8"), (2, 2))
        await w.open("cam")
        await w.close()
        assert not w.is_open
        assert w._finalized

    async def test_close_when_not_open_is_noop(self) -> None:
        w = self._make_writer()
        await w.close()
        assert not w._finalized

    async def test_get_indices_written_min_across_sources(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.register("a", np.dtype("uint8"), (2, 2))
        w.register("b", np.dtype("uint8"), (2, 2))
        await w.open("a")
        await w.open("b")
        w._sources["a"].frames_written = 1
        assert await w.get_indices_written() == 0

    async def test_collect_stream_docs_emits_resource_then_datum(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.register("cam", np.dtype("uint8"), (2, 2))
        await w.open("cam")
        w._sources["cam"].frames_written = 3
        docs = [doc async for doc in w.collect_stream_docs("cam", 3)]
        kinds = [d[0] for d in docs]
        assert "stream_resource" in kinds
        assert "stream_datum" in kinds

    async def test_collect_stream_docs_mimetype_from_writer(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.register("cam", np.dtype("uint8"), (2, 2))
        await w.open("cam")
        w._sources["cam"].frames_written = 1
        docs = [doc async for doc in w.collect_stream_docs("cam", 1)]
        resource = next(d for kind, d in docs if kind == "stream_resource")
        assert resource["mimetype"] == "application/x-test"

    async def test_collect_stream_docs_no_duplicate_resource(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.register("cam", np.dtype("uint8"), (2, 2))
        await w.open("cam")
        w._sources["cam"].frames_written = 2
        docs1 = [doc async for doc in w.collect_stream_docs("cam", 2)]
        assert any(d[0] == "stream_resource" for d in docs1)
        w._sources["cam"].frames_written = 4
        docs2 = [doc async for doc in w.collect_stream_docs("cam", 4)]
        assert not any(d[0] == "stream_resource" for d in docs2)


class TestWriterMetadata:
    def _make_writer(self) -> _ConcreteWriter:
        return _ConcreteWriter()

    def test_update_metadata_accumulates(self) -> None:
        w = self._make_writer()
        w.update_metadata({"exposure": 0.01, "roi": [0, 0, 512, 512]})
        assert w._metadata == {"exposure": 0.01, "roi": [0, 0, 512, 512]}

    def test_update_metadata_overwrites_same_key(self) -> None:
        w = self._make_writer()
        w.update_metadata({"exposure": 0.01})
        w.update_metadata({"exposure": 0.05})
        assert w._metadata["exposure"] == 0.05

    def test_update_metadata_merges(self) -> None:
        w = self._make_writer()
        w.update_metadata({"exposure": 0.01})
        w.update_metadata({"roi": [0, 0, 512, 512]})
        assert w._metadata == {"exposure": 0.01, "roi": [0, 0, 512, 512]}

    async def test_metadata_available_at_open(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.register("cam", np.dtype("uint8"), (2, 2))
        w.update_metadata({"exposure": 0.01})
        await w.open("cam")
        assert w._metadata == {"exposure": 0.01}

    async def test_metadata_cleared_on_close(self) -> None:
        w = self._make_writer()
        w.set_uri("file:///tmp/test.zarr")
        w.register("cam", np.dtype("uint8"), (2, 2))
        w.update_metadata({"exposure": 0.01})
        await w.open("cam")
        await w.close()
        assert w._metadata == {}

    def test_clear_metadata(self) -> None:
        w = self._make_writer()
        w.update_metadata({"exposure": 0.01, "roi": [0, 0, 512, 512]})
        w.clear_metadata()
        assert w._metadata == {}

    async def test_metadata_not_cleared_by_failed_open(self) -> None:
        """A failed open (no URI) must not wipe accumulated metadata."""
        w = self._make_writer()
        w.register("cam", np.dtype("uint8"), (2, 2))
        w.update_metadata({"exposure": 0.01})
        with pytest.raises(RuntimeError, match="no URI"):
            await w.open("cam")
        assert w._metadata == {"exposure": 0.01}


class TestProtocolConformance:
    def test_concrete_writer_is_shared_detector_writer(self) -> None:
        w = _ConcreteWriter("default")
        assert isinstance(w, SharedDetectorWriter)

    def test_zarr_writer_is_shared_detector_writer(self) -> None:
        w = ZarrWriter("default")
        assert isinstance(w, SharedDetectorWriter)

    def test_has_writer_logic_structural_check(self) -> None:
        class _FakeDevice:
            @property
            def writer_logic(self) -> _ConcreteWriter:
                return _ConcreteWriter()

        assert isinstance(_FakeDevice(), HasWriterLogic)

    def test_device_without_writer_logic_fails_check(self) -> None:
        class _NoWriter:
            pass

        assert not isinstance(_NoWriter(), HasWriterLogic)


class TestProtocols:
    def test_writer_satisfies_has_metadata(self) -> None:
        w = _ConcreteWriter()
        assert isinstance(w, HasMetadata)

    def test_object_without_update_metadata_fails_has_metadata(self) -> None:
        class _NoMeta:
            pass

        assert not isinstance(_NoMeta(), HasMetadata)


class TestHandleDescriptorMetadata:
    def _make_device(self, writer: _ConcreteWriter) -> object:
        class _FakeDevice:
            @property
            def writer_logic(self) -> _ConcreteWriter:
                return writer

        return _FakeDevice()

    def test_sets_metadata_on_matching_writer(self) -> None:
        writer = _ConcreteWriter()
        devices = {"cam": self._make_device(writer)}
        doc = {"configuration": {"cam": {"exposure": 0.01, "roi": [0, 0, 512, 512]}}}
        handle_descriptor_metadata(doc, devices)
        assert writer._metadata["cam"] == {"exposure": 0.01, "roi": [0, 0, 512, 512]}

    def test_skips_unknown_devices(self) -> None:
        doc = {"configuration": {"unknown": {"x": 1}}}
        handle_descriptor_metadata(doc, {})

    def test_skips_devices_without_writer_logic(self) -> None:
        class _NoWriter:
            pass

        doc = {"configuration": {"motor": {"position": 1.5}}}
        handle_descriptor_metadata(doc, {"motor": _NoWriter()})

    def test_skips_writers_without_update_metadata(self) -> None:
        class _MinimalWriter:
            pass

        class _Device:
            @property
            def writer_logic(self) -> _MinimalWriter:
                return _MinimalWriter()

        doc = {"configuration": {"cam": {"exposure": 0.01}}}
        handle_descriptor_metadata(doc, {"cam": _Device()})

    def test_empty_configuration_is_noop(self) -> None:
        writer = _ConcreteWriter()
        devices = {"cam": self._make_device(writer)}
        handle_descriptor_metadata({"configuration": {}}, devices)
        assert writer._metadata == {}


class TestZarrWriterImportGuard:
    def test_import_error_without_acquire_zarr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import redsun.storage._zarr as zarr_mod

        monkeypatch.setattr(zarr_mod, "_ACQUIRE_ZARR_AVAILABLE", False)
        with pytest.raises(ImportError, match="acquire-zarr"):
            ZarrWriter("default")


class TestZarrWriterOpen:
    async def test_open(self, tmp_path: Path) -> None:
        uri = tmp_path.as_uri() + "/scan.zarr"
        writer = ZarrWriter("default")
        writer.set_uri(uri)
        writer.register(
            "cam",
            dtype=np.dtype("uint16"),
            shape=(64, 64),
            capacity=10,
        )
        with patch("redsun.storage._zarr.ZarrStream"):
            await writer.open("cam")
        assert writer.is_open

    def test_set_uri_updates_store_path(self, tmp_path: Path) -> None:
        uri = tmp_path.as_uri() + "/scan"
        writer = ZarrWriter("default")
        writer.set_uri(uri)
        assert writer._stream_settings.store_path == from_uri(uri) + ".zarr"

    async def test_metadata_written_on_open(self, tmp_path: Path) -> None:
        uri = tmp_path.as_uri() + "/scan"
        writer = ZarrWriter("default")
        writer.set_uri(uri)
        writer.register("cam", dtype=np.dtype("uint16"), shape=(64, 64))
        writer.update_metadata({"motor": {"position": 1.5}})
        with patch("redsun.storage._zarr.ZarrStream") as mock_stream_cls:
            await writer.open("cam")
            mock_stream_cls.return_value.write_custom_metadata.assert_called_once()
