"""Tests for the catalog a session starts from its storage section."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx
import numpy as np
import ome_writers as ow
import pytest
import stamina
import yaml
from bluesky_tiled_plugins import TiledWriter
from event_model import compose_run, compose_stream_resource
from tiled.client import from_uri
from tiled.client.register import register
from tiled.server.simple import SimpleTiledServer

from redsun.catalog import CATALOG, CatalogAddress
from redsun.containers import AppContainer

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

SESSION = "catalog-session"


@pytest.fixture(autouse=True)
def no_retries() -> Iterator[None]:
    """Fail a request at once, where the `tiled` client would retry with backoff."""
    with stamina.set_testing(True):
        yield


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Callable[..., AppContainer]]:
    """Build containers from a session file, and shut each down afterwards."""
    built: list[AppContainer] = []

    def build(**sections: Any) -> AppContainer:
        config = {"schema_version": 1.0, "frontend": "pyqt", "name": SESSION}
        cfg_file = tmp_path / "session.yaml"
        cfg_file.write_text(yaml.dump({**config, **sections}))
        app = AppContainer.from_config(str(cfg_file))
        built.append(app)
        return app.build()

    yield build
    for app in built:
        app.shutdown()


def client_of(app: AppContainer) -> Any:
    """Return a client of the catalog *app* provides the address of."""
    address = app.virtual_container.try_require(CATALOG)
    assert address is not None
    return from_uri(address.uri)


def write_stack(directory: Path) -> Path:
    """Write a (t=2, z=3, 8, 8) OME-Zarr stack of ones into *directory*."""
    settings = ow.AcquisitionSettings(
        root_path=str(directory / "stack"),
        dtype="uint16",
        dimensions=(
            ow.Dimension(name="t", count=2, type="time", chunk_size=1),
            ow.Dimension(name="z", count=3, type="space", chunk_size=1),
            ow.Dimension(name="y", count=8, type="space", chunk_size=8),
            ow.Dimension(name="x", count=8, type="space", chunk_size=8),
        ),
        format=ow.OmeZarrFormat(backend="acquire-zarr"),
    )
    stream = ow.create_stream(settings)
    for _ in range(6):
        stream.append(np.ones((8, 8), "uint16"))
    stream.close()
    return directory / "stack.ome.zarr"


def write_frames(client: Any, uri: str) -> str:
    """Write a run through ``TiledWriter`` describing the stack at *uri* frame by frame."""
    writer = TiledWriter(client)
    bundle = compose_run()
    writer("start", bundle.start_doc)
    descriptor = bundle.compose_descriptor(
        name="primary",
        data_keys={
            "det": {
                "source": "camera",
                "dtype": "array",
                "shape": [8, 8],
                "dtype_numpy": "<u2",
                "external": "STREAM:",
            }
        },
    )
    writer("descriptor", descriptor.descriptor_doc)
    resource = compose_stream_resource(
        mimetype="application/x-ome-zarr",
        uri=uri,
        data_key="det",
        parameters={"chunk_shape": [1, 8, 8]},
        start=bundle.start_doc,
    )
    writer("stream_resource", resource.stream_resource_doc)
    for frame in range(6):
        writer(
            "stream_datum",
            resource.compose_stream_datum(
                indices={"start": frame, "stop": frame + 1},
                descriptor=descriptor.descriptor_doc,
            ),
        )
    writer("stop", bundle.compose_stop())
    return str(bundle.start_doc["uid"])


def write_table(directory: Path) -> Path:
    """Write a one-row table named after *directory* into it."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{directory.name}.csv").write_text("a,b\n1,2\n")
    return directory


@pytest.mark.parametrize(
    ("storage", "where"),
    [
        (lambda tmp: {"catalog": None}, "data/catalog-session/catalog"),
        (
            lambda tmp: {"base_dir": str(tmp / "root"), "catalog": None},
            "root/catalog-session/catalog",
        ),
    ],
    ids=["default-root", "configured-root"],
)
def test_the_catalog_starts_where_the_session_says(
    session: Callable[..., AppContainer],
    tmp_path: Path,
    storage: Callable[[Path], dict[str, Any]],
    where: str,
) -> None:
    session(storage=storage(tmp_path))

    assert (tmp_path / where / "catalog.db").is_file()


def test_the_catalog_lives_in_the_session_folder_whatever_its_name(
    session: Callable[..., AppContainer], tmp_path: Path
) -> None:
    """A name unsafe in a path gives the same folder the files and logs use."""
    app = session(name="Lab A: STED", storage={"catalog": None})

    assert app.path_provider.session_dir == tmp_path / "data" / "Lab_A_STED"
    assert (app.path_provider.session_dir / "catalog" / "catalog.db").is_file()


async def test_assets_read_back_only_from_readable_directories(
    session: Callable[..., AppContainer], tmp_path: Path
) -> None:
    """The session's directory and the configured ones; `tiled` checks on read."""
    app = session(storage={"catalog": {"readable": [str(tmp_path / "extra")]}})
    client = client_of(app)
    for directory in (
        app.path_provider.session_dir / "acquired",
        tmp_path / "extra",
        tmp_path / "outside",
    ):
        await register(client, write_table(directory), overwrite=False)

    assert client["acquired"].read().shape == (1, 2)
    assert client["extra"].read().shape == (1, 2)
    with pytest.raises(httpx.HTTPStatusError):
        client["outside"].read()


def test_a_catalog_that_fails_to_start_is_logged_and_skipped(
    session: Callable[..., AppContainer],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The session runs without a catalog rather than not at all."""
    occupied = tmp_path / "root" / SESSION / "catalog"
    occupied.parent.mkdir(parents=True)
    occupied.write_text("a file, where the catalog wants a directory")

    with caplog.at_level(logging.WARNING, logger="redsun"):
        app = session(storage={"base_dir": str(tmp_path / "root"), "catalog": None})

    assert app.is_built
    assert app.virtual_container.try_require(CATALOG) is None
    assert "Failed to start the catalog" in caplog.text
    # reported under a name no component can have
    assert "storage.catalog" in caplog.text


def test_a_server_failing_its_setup_is_stopped(
    session: Callable[..., AppContainer], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A server that started is not left running when what follows fails."""
    closed: list[SimpleTiledServer] = []
    close = SimpleTiledServer.close

    def record(server: SimpleTiledServer) -> None:
        closed.append(server)
        close(server)

    def fail() -> None:
        raise RuntimeError("no consolidator")

    monkeypatch.setattr(SimpleTiledServer, "close", record)
    monkeypatch.setattr("ome_tiled.bluesky.register_consolidator", fail)

    app = session(storage={"catalog": None})

    assert app.virtual_container.try_require(CATALOG) is None
    assert len(closed) == 1


def test_an_address_does_not_show_its_key(
    session: Callable[..., AppContainer],
) -> None:
    address = session(storage={"catalog": None}).virtual_container.require(CATALOG)

    assert "api_key" in address.uri
    assert "api_key" not in repr(address)
    assert address == CatalogAddress(address.uri)


def test_the_root_cannot_move_while_the_catalog_runs(
    session: Callable[..., AppContainer], tmp_path: Path
) -> None:
    """New files would land outside what the catalog can read."""
    app = session(storage={"catalog": None})
    root = app.path_provider.base_dir

    with pytest.raises(RuntimeError, match="catalog"):
        app.path_provider.set_base_dir(tmp_path / "elsewhere")

    assert app.path_provider.base_dir == root


def test_shutdown_stops_the_server(session: Callable[..., AppContainer]) -> None:
    app = session(storage={"catalog": None})
    client = client_of(app)

    app.shutdown()

    with pytest.raises(httpx.ConnectError):
        list(client)


def test_an_ome_zarr_run_reads_back_with_its_axis_names(
    session: Callable[..., AppContainer],
) -> None:
    """A ``TiledWriter`` stores the image as the store holds it, not as the frames."""
    app = session(storage={"catalog": None})
    store = write_stack(app.path_provider.session_dir / "acquired")
    client = client_of(app)

    det = client[write_frames(client, store.as_uri())]["primary"]["det"]

    assert det.structure().shape == (2, 3, 8, 8)
    assert det.structure().dims == ("t", "z", "y", "x")
    assert det.read().sum() == 2 * 3 * 8 * 8
