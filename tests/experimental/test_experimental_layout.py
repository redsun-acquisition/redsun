"""Tests for the window layout a session remembers between runs."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtWidgets import QApplication, QDockWidget, QWidget

from redsun.experimental import AsView, Placement
from redsun.experimental.containers.qt import Dock, QtAppContainer

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.qt

LEFT = QtNamespace.DockWidgetArea.LeftDockWidgetArea
RIGHT = QtNamespace.DockWidgetArea.RightDockWidgetArea


class Panel(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name


class Charts(Panel):
    pass


class LayoutApp(QtAppContainer):
    __slots__ = ()

    config: ClassVar[dict[str, Any]] = {"name": "layout-session"}

    panel: AsView[Panel]
    charts: AsView[Charts]


def _dock(app: QtAppContainer, name: str) -> QDockWidget:
    """Return the dock holding the view called *name*."""
    found = app.main_window.findChild(QDockWidget, name)
    assert isinstance(found, QDockWidget)
    return found


def test_a_dock_is_named_after_the_view_it_holds(
    qapp: QApplication, config_home: Path, build: Callable[..., QtAppContainer]
) -> None:
    """Qt places a dock by object name and drops one that has none."""
    app = build(LayoutApp)
    docks = app.main_window.findChildren(QDockWidget)

    assert {d.objectName() for d in docks} == {"panel", "charts"}


def test_a_layout_saved_by_one_run_is_restored_by_the_next(
    qapp: QApplication, config_home: Path, build: Callable[..., QtAppContainer]
) -> None:
    """Which is the whole of the deliverable, so it is driven end to end."""
    first = build(LayoutApp)
    first.main_window.addDockWidget(RIGHT, _dock(first, "charts"))
    first.save_layout()
    first.shutdown()

    second = build(LayoutApp)

    assert second.main_window.dockWidgetArea(_dock(second, "charts")) is RIGHT
    assert second.main_window.dockWidgetArea(_dock(second, "panel")) is LEFT


def test_a_session_this_user_has_never_run_keeps_what_its_views_asked_for(
    qapp: QApplication, config_home: Path, build: Callable[..., QtAppContainer]
) -> None:
    """Nothing saved is the common case, and it must not disturb the layout."""
    app = build(LayoutApp)

    assert app.main_window.dockWidgetArea(_dock(app, "charts")) is LEFT


def test_the_layout_goes_to_the_settings_file_as_text(
    qapp: QApplication, config_home: Path, build: Callable[..., QtAppContainer]
) -> None:
    """The settings file holds JSON, so a QByteArray cannot go in as it is."""
    build(LayoutApp).save_layout()

    written = json.loads((config_home / "layout-session.json").read_text())
    assert sorted(written) == ["window.geometry", "window.state"]
    assert base64.b64decode(written["window.state"])


def test_a_session_that_was_never_shown_writes_nothing(
    qapp: QApplication, config_home: Path, build: Callable[..., QtAppContainer]
) -> None:
    """``run`` asks for the save, so building alone leaves the file alone."""
    build(LayoutApp).shutdown()

    assert not (config_home / "layout-session.json").exists()
