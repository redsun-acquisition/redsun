"""The built-in storage view mirrors a shared provider, or degrades without one."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from redsun.containers import AppContainer, declare_presenter, declare_view
from redsun.presenter.builtins import StoragePresenter
from redsun.view.qt.builtins import StorageView

if TYPE_CHECKING:
    from collections.abc import Iterator

    from qtpy.QtWidgets import QApplication

pytestmark = pytest.mark.qt

BASE_DIR = Path.home() / "redsun-test-storage"


class _App(AppContainer):
    storage = declare_presenter(StoragePresenter, base_dir=str(BASE_DIR))
    widget = declare_view(StorageView)


class _NoPresenter(AppContainer):
    widget = declare_view(StorageView)


@pytest.fixture
def app(qapp: QApplication) -> Iterator[_App]:
    built = _App().build()
    yield built
    if built.is_built:
        built.shutdown()


def test_the_view_mirrors_the_shared_provider(app: _App) -> None:
    """The base directory shows, and editing it stays available."""
    assert app.widget._root_dir_edit.text() == str(BASE_DIR)
    assert app.widget._root_dir_btn.isEnabled()


def test_a_provider_update_reaches_the_view(app: _App) -> None:
    """The subscription is live: setting the base directory redraws the field."""
    updated = BASE_DIR / "elsewhere"

    app.storage.path_provider.set_base_dir(updated)

    assert app.widget._root_dir_edit.text() == str(updated)


def test_without_a_presenter_the_view_degrades(qapp: QApplication) -> None:
    """Nothing bound the key, so the view is a read-only placeholder."""
    app = _NoPresenter().build()
    try:
        assert app.widget._root_dir_edit.text() == "No root directory provided."
        assert not app.widget._root_dir_btn.isEnabled()
        assert app.virtual_container.subscriptions == []
    finally:
        app.shutdown()


def test_shutdown_releases_the_subscription(app: _App) -> None:
    """The regression this port exists to fix: the callback is taken back."""
    assert len(app.virtual_container.subscriptions) == 1
    # read before shutdown: a shut-down container owns no component
    storage, widget = app.storage, app.widget
    before = widget._root_dir_edit.text()

    app.shutdown()
    storage.path_provider.set_base_dir(BASE_DIR / "after-shutdown")

    assert widget._root_dir_edit.text() == before
    assert app.virtual_container.subscriptions == []
