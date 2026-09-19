"""A session with a catalog key starts a catalog and hands out its address."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import stamina
from tiled.client import from_uri

from redsun.catalog import CatalogAddress
from redsun.experimental import AsPresenter, Session

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from .conftest import BuildSession

CATALOG: dict[str, Any] = {"name": "catalog-session", "storage": {"catalog": None}}


@pytest.fixture(autouse=True)
def no_retries() -> Iterator[None]:
    """Fail a request at once, where the `tiled` client would retry with backoff."""
    with stamina.set_testing(True):
        yield


class Recorder:
    """Presenter needing the catalog."""

    def __init__(self, name: str, /, address: CatalogAddress) -> None:
        self.name = name
        self.address = address


class Optional:
    """Presenter using the catalog when the session has one."""

    def __init__(self, name: str, /, address: CatalogAddress | None = None) -> None:
        self.name = name
        self.address = address


class RecorderApp(Session):
    recorder: AsPresenter[Recorder]


class OptionalApp(Session):
    optional: AsPresenter[Optional]


def test_a_component_reaches_the_catalog_by_its_address(
    build: BuildSession, data_directory: Path
) -> None:
    app = build(RecorderApp, CATALOG)

    assert (data_directory / "catalog-session" / "catalog" / "catalog.db").is_file()
    assert list(from_uri(app.recorder.address.uri)) == []


@pytest.mark.parametrize(
    ("config", "has_address"),
    [(CATALOG, True), ({"name": "catalog-session"}, False)],
    ids=["with-catalog", "without"],
)
def test_an_optional_address_is_none_without_a_catalog(
    build: BuildSession, config: dict[str, Any], has_address: bool
) -> None:
    app = build(OptionalApp, config)

    assert isinstance(app.optional.address, CatalogAddress) is has_address


def test_the_root_cannot_move_while_the_catalog_runs(
    build: BuildSession, tmp_path: Path
) -> None:
    app = build(OptionalApp, CATALOG)

    with pytest.raises(RuntimeError, match="catalog"):
        app.path_provider.set_base_dir(tmp_path / "elsewhere")


def test_shutdown_stops_the_server(build: BuildSession) -> None:
    app = build(RecorderApp, CATALOG)
    client = from_uri(app.recorder.address.uri)

    app.shutdown()

    with pytest.raises(httpx.ConnectError):
        list(client)


def test_a_catalog_that_fails_to_start_is_logged_and_skipped(
    build: BuildSession, data_directory: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The session runs without a catalog rather than not at all."""
    occupied = data_directory / "catalog-session" / "catalog"
    occupied.parent.mkdir(parents=True)
    occupied.write_text("a file, where the catalog wants a directory")

    with caplog.at_level(logging.ERROR, logger="redsun"):
        app = build(OptionalApp, CATALOG)

    assert app.optional.address is None
    assert "Failed to start the catalog" in caplog.text
