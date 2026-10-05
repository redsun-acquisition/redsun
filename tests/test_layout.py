"""Tests for the window layout a session remembers between runs."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from mock_bundle.panels import Panel
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtWidgets import QApplication, QDockWidget

from redsun import AsView, Placement
from redsun.qt import Dock, QtSession

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.qt

LEFT = QtNamespace.DockWidgetArea.LeftDockWidgetArea
RIGHT = QtNamespace.DockWidgetArea.RightDockWidgetArea


class Charts(Panel):
    placement: Placement = Dock("right")


class LayoutApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "layout-session"}

    panel: AsView[Panel]
    charts: AsView[Charts]


def _dock(app: QtSession, name: str) -> QDockWidget:
    """Return the dock holding the view called *name*."""
    found = app.main_window.findChild(QDockWidget, name)
    assert isinstance(found, QDockWidget)
    return found


def test_a_dock_is_named_after_the_view_it_holds(
    qapp: QApplication, config_home: Path, build: Callable[..., QtSession]
) -> None:
    """Name each dock after its view, since Qt restores a dock by its object name."""
    app = build(LayoutApp)
    docks = app.main_window.findChildren(QDockWidget)

    assert {d.objectName() for d in docks} == {"panel", "charts"}


def test_a_layout_saved_by_one_run_is_restored_by_the_next(
    qapp: QApplication, config_home: Path, build: Callable[..., QtSession]
) -> None:
    """Restore in the next run the dock layout one run saved."""
    first = build(LayoutApp)
    first.main_window.addDockWidget(LEFT, _dock(first, "charts"))
    first.save_layout()
    first.shutdown()

    second = build(LayoutApp)

    assert second.main_window.dockWidgetArea(_dock(second, "charts")) is LEFT
    assert second.main_window.dockWidgetArea(_dock(second, "panel")) is LEFT


def test_a_dock_kept_away_from_its_placement_is_logged(
    qapp: QApplication,
    config_home: Path,
    build: Callable[..., QtSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log each dock the saved layout keeps away from the edge its placement asks for."""
    first = build(LayoutApp)
    first.main_window.addDockWidget(LEFT, _dock(first, "charts"))
    first.save_layout()
    first.shutdown()

    build(LayoutApp)

    assert "'charts' stays on the left, where it was left" in caplog.text
    assert "'panel'" not in caplog.text


def test_a_session_this_user_has_never_run_keeps_what_its_views_asked_for(
    qapp: QApplication, config_home: Path, build: Callable[..., QtSession]
) -> None:
    """Keep the docks where the views asked when no layout was saved."""
    app = build(LayoutApp)

    assert app.main_window.dockWidgetArea(_dock(app, "charts")) is RIGHT
    assert app.main_window.dockWidgetArea(_dock(app, "panel")) is LEFT


def test_the_layout_goes_to_the_settings_file_as_text(
    qapp: QApplication, config_home: Path, build: Callable[..., QtSession]
) -> None:
    """Write the layout to the JSON settings file as base64 text."""
    build(LayoutApp).save_layout()

    written = json.loads((config_home / "layout-session.json").read_text())
    assert sorted(written) == ["window.geometry", "window.state"]
    assert base64.b64decode(written["window.state"])


def test_a_session_that_was_never_shown_writes_nothing(
    qapp: QApplication, config_home: Path, build: Callable[..., QtSession]
) -> None:
    """Write no layout for a session that was built but never run."""
    build(LayoutApp).shutdown()

    assert not (config_home / "layout-session.json").exists()
