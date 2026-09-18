"""Tests for the catalog a session starts from its storage section."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import stamina
import yaml
from tiled.client import from_uri
from tiled.client.register import register

from redsun.catalog import CATALOG
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
        config = {"schema_version": 1.0, "frontend": "pyqt", "session": SESSION}
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


async def test_assets_read_back_only_from_readable_directories(
    session: Callable[..., AppContainer], tmp_path: Path
) -> None:
    """The session's directory and the configured ones; `tiled` checks on read."""
    app = session(storage={"catalog": {"readable": [str(tmp_path / "extra")]}})
    client = client_of(app)
    for directory in (
        app.path_provider.base_dir / SESSION / "acquired",
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

    with caplog.at_level(logging.ERROR, logger="redsun"):
        app = session(storage={"base_dir": str(tmp_path / "root"), "catalog": None})

    assert app.is_built
    assert app.virtual_container.try_require(CATALOG) is None
    assert "Failed to start the catalog" in caplog.text


def test_shutdown_stops_the_server(session: Callable[..., AppContainer]) -> None:
    app = session(storage={"catalog": None})
    client = client_of(app)

    app.shutdown()

    with pytest.raises(httpx.ConnectError):
        list(client)
