"""Tests for the window layout a session remembers between runs."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

import pytest
from app_model.backends.qt import QModelMenu
from mock_bundle.panels import Panel
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QAction
from qtpy.QtWidgets import QApplication, QDockWidget, QWidget

from redsun import AsView, Declare, Placement
from redsun.qt import WINDOW_MENU, Dock, QtSession

if TYPE_CHECKING:
    from pathlib import Path

    from redsun.testing import BuildSession

pytestmark = pytest.mark.qt

LEFT = QtNamespace.DockWidgetArea.LeftDockWidgetArea
RIGHT = QtNamespace.DockWidgetArea.RightDockWidgetArea
TOP = QtNamespace.DockWidgetArea.TopDockWidgetArea
BOTTOM = QtNamespace.DockWidgetArea.BottomDockWidgetArea


class Charts(Panel):  # type: ignore[misc]
    placement: Placement = Dock("right")


class LayoutApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "layout-session"}

    panel: AsView[Panel]
    charts: AsView[Charts]


class Grouped(Panel):  # type: ignore[misc]
    placement: Placement = Dock("left", group="tools")


class GroupedRight(Panel):  # type: ignore[misc]
    placement: Placement = Dock("right", group="tools")


class GroupedApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "grouped-session"}

    first: AsView[Grouped]
    second: AsView[Grouped]
    alone: AsView[Panel]
    other_edge: AsView[GroupedRight]


class TakesPlacement(Panel):  # type: ignore[misc]
    def __init__(self, name: str, parent: QWidget, placement: str = "") -> None:
        super().__init__(name, parent)


class Stages(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "stages-session"}

    upper: Annotated[AsView[Panel], Declare(placement=Dock("top"))]
    lower: Annotated[AsView[Panel], Declare(placement="bottom")]
    default: AsView[Panel]


class TakesPlacementApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "takes-placement"}

    taking: AsView[TakesPlacement]


class Fragile(Panel):  # type: ignore[misc]
    placement: Placement = Dock("right")

    def __init__(self, name: str, parent: QWidget, fail: bool = False) -> None:
        if fail:
            raise RuntimeError("no detector attached")
        super().__init__(name, parent)


class FragileApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "fragile-session"}

    panel: AsView[Panel]
    fragile: AsView[Fragile]


def builtin_session(
    plugin_id: str, presenter: str | None, placement: str | None
) -> QtSession:
    """Return a session declaring one built-in view, and its presenter, from a file."""
    view: dict[str, Any] = {"plugin_name": "redsun", "plugin_id": plugin_id}
    if placement is not None:
        view["placement"] = placement
    config: dict[str, Any] = {
        "session": f"placed-{plugin_id}-{placement}",
        "views": {"view": view},
    }
    if presenter is not None:
        config["presenters"] = {
            "presenter": {"plugin_name": "redsun", "plugin_id": presenter}
        }
    return QtSession.from_config(config)


def _dock(app: QtSession, name: str) -> QDockWidget:
    """Return the dock holding the view called *name*."""
    found = app.main_window.findChild(QDockWidget, name)
    assert isinstance(found, QDockWidget)
    return found


def test_a_dock_is_named_after_the_view_it_holds(
    qapp: QApplication, build: BuildSession
) -> None:
    """Name each dock after its view, since Qt restores a dock by its object name."""
    app = build(LayoutApp)
    docks = app.main_window.findChildren(QDockWidget)

    assert {d.objectName() for d in docks} == {"panel", "charts"}


def test_a_layout_saved_by_one_run_is_restored_by_the_next(
    qapp: QApplication, build: BuildSession
) -> None:
    """Restore in the next run the dock layout one run saved."""
    first = build(LayoutApp)
    first.main_window.addDockWidget(LEFT, _dock(first, "charts"))
    first.save_layout()
    first.shutdown()

    second = build(LayoutApp)

    assert second.main_window.dockWidgetArea(_dock(second, "charts")) is LEFT
    assert second.main_window.dockWidgetArea(_dock(second, "panel")) is LEFT


def test_a_changed_placement_skips_the_saved_layout(
    qapp: QApplication,
    build: BuildSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Start every dock where its placement says once a placement changed since the layout was saved."""
    first = build(LayoutApp)
    first.main_window.addDockWidget(LEFT, _dock(first, "charts"))
    first.save_layout()
    first.shutdown()

    second = build(LayoutApp, {"views": {"panel": {"placement": "top"}}})

    assert second.main_window.dockWidgetArea(_dock(second, "charts")) is RIGHT
    assert second.main_window.dockWidgetArea(_dock(second, "panel")) is TOP
    assert "placed differently from when" in caplog.text


def test_a_layout_saved_before_placements_were_recorded_is_restored(
    qapp: QApplication, config_home: Path, build: BuildSession
) -> None:
    """Restore a saved layout whose settings file records no placements, as an older release wrote it."""
    first = build(LayoutApp)
    first.main_window.addDockWidget(LEFT, _dock(first, "charts"))
    first.save_layout()
    first.shutdown()
    path = config_home / "layout-session.json"
    written = json.loads(path.read_text())
    del written["window.layout"]
    path.write_text(json.dumps(written))

    second = build(LayoutApp, {"views": {"panel": {"placement": "top"}}})

    assert second.main_window.dockWidgetArea(_dock(second, "charts")) is LEFT


def test_a_view_that_fails_to_build_keeps_the_saved_layout(
    qapp: QApplication, build: BuildSession
) -> None:
    """Restore the saved layout when a view that built before fails, its placeholder keeping its place."""
    first = build(FragileApp)
    first.main_window.addDockWidget(RIGHT, _dock(first, "panel"))
    first.save_layout()
    first.shutdown()

    second = build(FragileApp, {"views": {"fragile": {"fail": True}}})

    assert "fragile" not in second.views
    assert second.main_window.dockWidgetArea(_dock(second, "panel")) is RIGHT


def test_reset_layout_returns_the_docks_to_their_placements(
    qapp: QApplication, build: BuildSession
) -> None:
    """Put a restored layout back where the placements say when Reset layout runs."""
    first = build(LayoutApp)
    first.main_window.addDockWidget(LEFT, _dock(first, "charts"))
    first.save_layout()
    first.shutdown()
    second = build(LayoutApp)

    second.model.commands.execute_command("layout-session.reset_layout")

    assert second.main_window.dockWidgetArea(_dock(second, "charts")) is RIGHT


def test_the_window_menu_brings_back_a_closed_dock(
    qapp: QApplication, build: BuildSession
) -> None:
    """Show a dock closed with its X button unchecked in the Window menu, and show it again from there."""
    app = build(LayoutApp)
    dock = _dock(app, "charts")
    menu = app.main_window.findChild(QModelMenu, WINDOW_MENU)
    assert isinstance(menu, QModelMenu)
    action = menu.findAction("layout-session.toggle_dock.charts")
    assert isinstance(action, QAction)

    dock.close()
    menu.aboutToShow.emit()
    checked = action.isChecked()
    action.trigger()

    assert menu.title() == "Window"
    assert not checked
    assert not dock.isHidden()


def test_a_session_this_user_has_never_run_keeps_what_its_views_asked_for(
    qapp: QApplication, build: BuildSession
) -> None:
    """Keep the docks where the views asked when no layout was saved."""
    app = build(LayoutApp)

    assert app.main_window.dockWidgetArea(_dock(app, "charts")) is RIGHT
    assert app.main_window.dockWidgetArea(_dock(app, "panel")) is LEFT


def test_the_layout_goes_to_the_settings_file_as_text(
    qapp: QApplication, config_home: Path, build: BuildSession
) -> None:
    """Write the layout to the JSON settings file as base64 text."""
    build(LayoutApp).save_layout()

    written = json.loads((config_home / "layout-session.json").read_text())
    assert sorted(written) == ["window.geometry", "window.layout", "window.state"]
    assert base64.b64decode(written["window.state"])


def test_a_session_that_was_never_shown_writes_nothing(
    qapp: QApplication, config_home: Path, build: BuildSession
) -> None:
    """Write no layout for a session that was built but never run."""
    build(LayoutApp).shutdown()

    assert not (config_home / "layout-session.json").exists()


def test_docks_of_one_edge_and_group_open_as_tabs(
    qapp: QApplication, build: BuildSession
) -> None:
    """Tab the docks of one edge and group together, and stack the rest beside them."""
    app = build(GroupedApp)
    window = app.main_window

    assert window.tabifiedDockWidgets(_dock(app, "first")) == [_dock(app, "second")]
    assert window.tabifiedDockWidgets(_dock(app, "alone")) == []
    assert window.tabifiedDockWidgets(_dock(app, "other_edge")) == []


@pytest.mark.parametrize(
    ("plugin_id", "presenter", "default"),
    [
        ("acquisition", "acquisition", LEFT),
        ("lights", "lights", RIGHT),
        ("positioner", "positioner", RIGHT),
        ("logs", None, BOTTOM),
    ],
)
def test_a_built_in_view_docks_where_its_entry_places_it(
    qapp: QApplication,
    build: BuildSession,
    plugin_id: str,
    presenter: str | None,
    default: QtNamespace.DockWidgetArea,
) -> None:
    """Dock each built-in view where its entry's placement says, on its own edge without one."""
    placed = build(builtin_session(plugin_id, presenter, "top"))
    unplaced = build(builtin_session(plugin_id, presenter, None))

    assert placed.main_window.dockWidgetArea(_dock(placed, "view")) is TOP
    assert unplaced.main_window.dockWidgetArea(_dock(unplaced, "view")) is default


def test_each_declaration_of_one_view_class_docks_where_it_says(
    qapp: QApplication, build: BuildSession
) -> None:
    """Dock declarations of one class where each places it, as an object or a word, else on the class's edge."""
    app = build(Stages)

    areas = {
        name: app.main_window.dockWidgetArea(_dock(app, name))
        for name in ("upper", "lower", "default")
    }
    assert areas == {"upper": TOP, "lower": BOTTOM, "default": LEFT}


@pytest.mark.parametrize(
    ("config", "missing", "reason"),
    [
        (
            {"views": {"panel": {"placement": "middle"}}},
            "panel",
            "names nothing Qt attaches",
        ),
        (
            {
                "presenters": {
                    "lights": {
                        "plugin_name": "redsun",
                        "plugin_id": "lights",
                        "placement": "left",
                    }
                }
            },
            "lights",
            "only a view takes a 'placement'",
        ),
    ],
)
def test_a_placement_that_cannot_be_used_skips_only_its_component(
    qapp: QApplication,
    build: BuildSession,
    caplog: pytest.LogCaptureFixture,
    config: dict[str, Any],
    missing: str,
    reason: str,
) -> None:
    """Skip a component given an unreadable or misplaced placement, and build the rest."""
    app = build(LayoutApp, config)

    assert missing not in {**app.views, **app.presenters}
    assert "charts" in app.views
    assert reason in caplog.text


def test_a_view_taking_placement_itself_is_refused(
    qapp: QApplication, build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Refuse a view whose constructor takes the key a view declaration reserves."""
    app = build(TakesPlacementApp)

    assert "taking" not in app.views
    assert "reserves for the session" in caplog.text
