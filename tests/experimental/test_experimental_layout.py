"""Tests for the window layout a session remembers between runs."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtWidgets import QDockWidget, QWidget

from redsun.experimental import AsView, Placement
from redsun.experimental.containers.qt import Dock, QtAppContainer

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.qt


class Panel(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name


class Charts(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name


class LayoutApp(QtAppContainer):
    __slots__ = ()

    config: ClassVar[dict[str, Any]] = {"name": "layout-session"}

    panel: AsView[Panel]
    charts: AsView[Charts]


@pytest.fixture
def config_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Keep the settings out of the user's own configuration directory."""
    monkeypatch.setattr(
        "redsun.experimental._settings.user_config_dir", lambda *a, **k: str(tmp_path)
    )
    return tmp_path


def _dock(app: QtAppContainer, name: str) -> QDockWidget:
    """Return the dock holding the view called *name*."""
    found = app.main_window.findChild(QDockWidget, name)
    assert isinstance(found, QDockWidget)
    return found


def test_a_dock_is_named_after_the_view_it_holds(qapp: Any, config_home: Path) -> None:
    """Qt places a dock by object name and drops one that has none."""
    app = LayoutApp().build()
    try:
        assert {d.objectName() for d in app.main_window.findChildren(QDockWidget)} == {
            "panel",
            "charts",
        }
    finally:
        app.shutdown()


def test_a_layout_saved_by_one_run_is_restored_by_the_next(
    qapp: Any, config_home: Path
) -> None:
    """Which is the whole of the deliverable, so it is driven end to end."""
    first = LayoutApp().build()
    try:
        first.main_window.addDockWidget(
            QtNamespace.DockWidgetArea.RightDockWidgetArea, _dock(first, "charts")
        )
        first.save_layout()
    finally:
        first.shutdown()

    second = LayoutApp().build()
    try:
        assert second.main_window.dockWidgetArea(_dock(second, "charts")) is (
            QtNamespace.DockWidgetArea.RightDockWidgetArea
        )
        assert second.main_window.dockWidgetArea(_dock(second, "panel")) is (
            QtNamespace.DockWidgetArea.LeftDockWidgetArea
        )
    finally:
        second.shutdown()


def test_a_session_this_user_has_never_run_keeps_what_its_views_asked_for(
    qapp: Any, config_home: Path
) -> None:
    """Nothing saved is the common case, and it must not disturb the layout."""
    app = LayoutApp().build()
    try:
        assert app.main_window.dockWidgetArea(_dock(app, "charts")) is (
            QtNamespace.DockWidgetArea.LeftDockWidgetArea
        )
    finally:
        app.shutdown()


def test_the_layout_goes_to_the_settings_file_as_text(
    qapp: Any, config_home: Path
) -> None:
    """The settings file holds JSON, so a QByteArray cannot go in as it is."""
    app = LayoutApp().build()
    try:
        app.save_layout()
    finally:
        app.shutdown()

    written = json.loads((config_home / "layout-session.json").read_text())
    assert sorted(written) == ["window.geometry", "window.state"]
    assert base64.b64decode(written["window.state"])


def test_a_session_that_was_never_shown_writes_nothing(
    qapp: Any, config_home: Path
) -> None:
    """``run`` asks for the save, so building alone leaves the file alone."""
    LayoutApp().build().shutdown()
    assert not (config_home / "layout-session.json").exists()
