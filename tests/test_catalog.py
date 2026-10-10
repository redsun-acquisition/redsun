"""A session with a catalog key starts a catalog and hands out its address."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import stamina
from tiled.client import from_uri

from redsun import AsPresenter, Session
from redsun.catalog import CatalogAddress

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from pathlib import Path

    from redsun.testing import BuildSession

CATALOG: dict[str, Any] = {"session": "catalog-session", "storage": {"catalog": None}}


@pytest.fixture(autouse=True)
def no_retries() -> Iterator[None]:
    """Fail a request at once, where the `tiled` client would retry with backoff."""
    with stamina.set_testing(True):
        yield


class AddressHolder:
    """Presenter needing the catalog."""

    def __init__(self, name: str, *, address: CatalogAddress) -> None:
        self.name = name
        self.address = address


class MaybeCatalogReader:
    """Presenter using the catalog when the session has one."""

    def __init__(self, name: str, *, address: CatalogAddress | None = None) -> None:
        self.name = name
        self.address = address


class AddressApp(Session):
    holder: AsPresenter[AddressHolder]


class OptionalApp(Session):
    optional: AsPresenter[MaybeCatalogReader]


class SharedCatalogApp(Session):
    holder: AsPresenter[AddressHolder]
    optional: AsPresenter[MaybeCatalogReader]


@pytest.fixture(scope="module")
def catalog_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return the data folder of the catalog the reading tests share."""
    return tmp_path_factory.mktemp("shared-catalog")


@pytest.fixture(scope="module")
def catalog_app(catalog_root: Path) -> Generator[SharedCatalogApp, None, None]:
    """Build one session with a catalog for the tests that only read from it.

    Starting a catalog takes seconds, so the tests that change nothing share
    one. The folders are patched here: the per-test fixtures doing it run
    after a module's fixtures.
    """
    with pytest.MonkeyPatch.context() as patch:
        for target in (
            "redsun.path_provider.user_data_dir",
            "redsun.log.user_data_dir",
            "redsun._settings.user_config_dir",
        ):
            patch.setattr(target, lambda *a, **k: str(catalog_root))
        app = SharedCatalogApp(CATALOG).build()
        try:
            yield app
        finally:
            app.shutdown()


def test_a_component_reaches_the_catalog_by_its_address(
    catalog_app: SharedCatalogApp, catalog_root: Path
) -> None:
    """Start a catalog in the session directory and give a component its address."""
    assert (catalog_root / "catalog-session" / "catalog" / "catalog.db").is_file()
    assert list(from_uri(catalog_app.holder.address.uri)) == []


def test_an_optional_address_is_given_with_a_catalog(
    catalog_app: SharedCatalogApp,
) -> None:
    """Give an optional catalog address when the session starts a catalog."""
    assert isinstance(catalog_app.optional.address, CatalogAddress)


def test_an_optional_address_is_none_without_a_catalog(build: BuildSession) -> None:
    """Give no optional catalog address when the session starts no catalog."""
    app = build(OptionalApp, {"session": "catalog-session"})

    assert app.optional.address is None


def test_the_root_cannot_move_while_the_catalog_runs(
    catalog_app: SharedCatalogApp, tmp_path: Path
) -> None:
    """Refuse to move the storage root while the catalog runs."""
    with pytest.raises(RuntimeError, match="catalog"):
        catalog_app.path_provider.set_base_dir(tmp_path / "elsewhere")


def test_shutdown_stops_the_server(build: BuildSession) -> None:
    """Stop the catalog server when the session shuts down."""
    app = build(AddressApp, CATALOG)
    client = from_uri(app.holder.address.uri)

    app.shutdown()

    with pytest.raises(httpx.ConnectError):
        list(client)


def test_a_catalog_that_fails_to_start_is_logged_and_skipped(
    build: BuildSession, data_directory: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Log a catalog that fails to start and run the session without it."""
    occupied = data_directory / "catalog-session" / "catalog"
    occupied.parent.mkdir(parents=True)
    occupied.write_text("a file, where the catalog wants a directory")

    with caplog.at_level(logging.ERROR, logger="redsun"):
        app = build(OptionalApp, CATALOG)

    assert app.optional.address is None
    assert "Failed to start the catalog" in caplog.text
