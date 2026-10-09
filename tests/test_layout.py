"""Tests for the window layout a session remembers between runs."""

from __future__ import annotations

import base64
import json
import logging
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

import pytest
from app_model.backends.qt import QModelMainWindow, QModelMenu
from app_model.types import Action, MenuRule
from mock_bundle.panels import Panel
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QAction
from qtpy.QtWidgets import (
    QApplication,
    QDockWidget,
    QMainWindow,
    QSplitter,
    QTabWidget,
    QWidget,
)

from redsun import (
    AsHook,
    AsView,
    Column,
    Declare,
    Placement,
    Row,
    Tabs,
    WindowLayout,
)
from redsun.qt import WINDOW_MENU, Central, Dock, MenuItem, QtSession, attach

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


class FragileByProperty(QWidget):
    def __init__(self, name: str, parent: QWidget, fail: bool = False) -> None:
        if fail:
            raise RuntimeError("no detector attached")
        super().__init__(parent)
        self.name = name

    @property
    def placement(self) -> Placement:
        return Dock("right")


class FragileByPropertyApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "fragile-property-session"}

    panel: AsView[Panel]
    fragile: AsView[FragileByProperty]


class AddsItsOwnDock(Panel):  # type: ignore[misc]
    placement: Placement = Dock("right")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(name, parent)
        if isinstance(parent, QMainWindow):
            parent.addDockWidget(RIGHT, QDockWidget("extra", parent))


class OwnDocksApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "own-docks-session"}

    first: AsView[AddsItsOwnDock]
    second: AsView[AddsItsOwnDock]


class AddsNotes:
    def configure_main_view(self, view: QMainWindow) -> None:
        notes = QDockWidget("notes", view)
        notes.setObjectName("notes")
        view.addDockWidget(LEFT, notes)


class HookDockApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "hook-dock-session"}

    panel: AsView[Panel]
    configure_main_view: AsHook[AddsNotes]


class SetsItsOwnMenuBar:
    def configure_main_view(self, view: QModelMainWindow) -> None:
        view.setModelMenuBar({WINDOW_MENU: "Window"})


class HookMenuBarApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "hook-menu-bar-session"}

    panel: AsView[Panel]
    configure_main_view: AsHook[SetsItsOwnMenuBar]


class OpensLog(QAction):
    placement: Placement = MenuItem("Window")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(name, parent)
        self.name = name


class WindowItemApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "window-item-session"}

    panel: AsView[Panel]
    log: AsView[OpensLog]


class LaidOutApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "laid-out-session"}

    a: AsView[Panel]
    b: AsView[Panel]
    c: AsView[Panel]
    d: AsView[Panel]
    e: AsView[Panel]
    p: AsView[Panel]
    q: AsView[Panel]
    r: AsView[Panel]

    def window_layout(self) -> WindowLayout | None:
        return WindowLayout(
            regions={
                "left": Column(Row("a", "b"), Tabs("c", "d", current="d")),
                "right": "e",
                "center": Row("p", Tabs("q", "r", current="r")),
            },
            hidden=["e"],
        )


class PropertyApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "property-session"}

    panel: AsView[Panel]
    old: AsView[FragileByProperty]

    def window_layout(self) -> WindowLayout | None:
        return WindowLayout(regions={"left": "panel"})


class FragileLaidOutApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "fragile-laid-out-session"}

    panel: AsView[Panel]
    fragile: AsView[Fragile]

    def window_layout(self) -> WindowLayout | None:
        return WindowLayout(regions={"left": Tabs("panel", "fragile")})


class SeveralCentralApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "several-central-session"}

    first: Annotated[AsView[Panel], Declare(placement=Central())]
    second: Annotated[AsView[Panel], Declare(placement=Central())]
    tool: Annotated[AsView[Panel], Declare(placement=Dock("top", group="g"))]
    other: Annotated[AsView[Panel], Declare(placement=Dock("top", group="g"))]


class SizedApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "sized-session"}

    a: AsView[Panel]
    b: AsView[Panel]
    p: Annotated[AsView[Panel], Declare(placement=Central())]
    q: Annotated[AsView[Panel], Declare(placement=Central())]
    r: Annotated[AsView[Panel], Declare(placement=Central())]

    def window_layout(self) -> WindowLayout | None:
        return WindowLayout(
            regions={
                "left": Column("a", "b", sizes=(1, 3)),
                "center": Row("p", Tabs("q", "r"), sizes=(1, 2)),
            },
            sizes={"left": 0.25},
        )


class TabbedSizesApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "tabbed-sizes-session"}

    a: AsView[Panel]
    b: AsView[Panel]
    c: AsView[Panel]
    p: Annotated[AsView[Panel], Declare(placement=Central())]

    def window_layout(self) -> WindowLayout | None:
        return WindowLayout(regions={"left": Column(Tabs("a", "b"), "c", sizes=(1, 3))})


class OwnPresentApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "own-present-session"}

    panel: AsView[Panel]

    def present(self) -> None:
        attach(self.main_window, self.views)


class PropertyLaidOutApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "property-laid-out-session"}

    panel: AsView[Panel]
    old: AsView[FragileByProperty]

    def window_layout(self) -> WindowLayout | None:
        return WindowLayout(regions={"left": Column("panel", "old")})


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


def _shown(app: QtSession) -> None:
    """Show *app*'s window at a known size, and let Qt lay it out, as `run` would."""
    app.main_window.resize(1200, 800)
    app.show()
    QApplication.processEvents()


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


@pytest.mark.parametrize("session", [FragileApp, FragileByPropertyApp])
def test_a_view_that_fails_to_build_keeps_the_saved_layout(
    qapp: QApplication, build: BuildSession, session: type[QtSession]
) -> None:
    """Restore the saved layout when a view that built before fails, its placement declared or answered by a property."""
    first = build(session)
    first.main_window.addDockWidget(RIGHT, _dock(first, "panel"))
    first.save_layout()
    first.shutdown()

    second = build(session, {"views": {"fragile": {"fail": True}}})

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

    bar = app.main_window.menuBar()
    assert bar is not None
    assert menu.menuAction() in bar.actions()
    assert menu.title() == "Window"
    assert not checked
    assert not dock.isHidden()


def test_a_dock_a_view_adds_itself_gets_no_toggle(
    qapp: QApplication, build: BuildSession
) -> None:
    """Build a session whose views add unnamed docks of their own, with a toggle for each view's dock alone."""
    app = build(OwnDocksApp)
    menu = app.main_window.findChild(QModelMenu, WINDOW_MENU)
    assert isinstance(menu, QModelMenu)
    menu.aboutToShow.emit()

    toggles = [action.text() for action in menu.actions() if action.isCheckable()]

    assert toggles == ["first", "second"]


def test_the_window_menu_brings_back_a_dock_the_hook_added(
    qapp: QApplication, build: BuildSession
) -> None:
    """Show again from the Window menu a dock the main-view hook added and the user closed."""
    app = build(HookDockApp)
    notes = app.main_window.findChild(QDockWidget, "notes")
    assert isinstance(notes, QDockWidget)
    menu = app.main_window.findChild(QModelMenu, WINDOW_MENU)
    assert isinstance(menu, QModelMenu)

    notes.close()
    action = menu.findAction("hook-dock-session.toggle_dock.notes")
    assert isinstance(action, QAction)
    action.trigger()

    assert not notes.isHidden()


def test_a_hook_menu_bar_with_the_window_menu_shows_it_once(
    qapp: QApplication, build: BuildSession
) -> None:
    """Show one Window menu when the main-view hook sets a menu bar that includes it."""
    app = build(HookMenuBarApp)
    bar = app.main_window.menuBar()
    assert bar is not None

    titles = [action.text() for action in bar.actions()]

    assert titles.count("Window") == 1


def test_a_view_placed_in_a_window_menu_joins_the_session_one(
    qapp: QApplication, build: BuildSession
) -> None:
    """Show a view placed in a menu named Window in the one Window menu, there still after the menu changes."""
    app = build(WindowItemApp)
    bar = app.main_window.menuBar()
    assert bar is not None
    menu = app.main_window.findChild(QModelMenu, WINDOW_MENU)
    assert isinstance(menu, QModelMenu)
    added = Action(
        id="window-item-session.extra",
        title="Extra",
        callback=lambda: None,
        menus=[MenuRule(id=WINDOW_MENU)],
    )

    dispose = app.model.register_action(added)
    titles = [action.text() for action in bar.actions()]
    items = [action.text() for action in menu.actions()]
    dispose()

    assert titles.count("Window") == 1
    assert "log" in items
    assert "Extra" in items


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
    assert sorted(written) == [
        "window.center",
        "window.geometry",
        "window.layout",
        "window.state",
    ]
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


def test_a_declared_layout_arranges_the_docks(
    qapp: QApplication, build: BuildSession
) -> None:
    """Split, stack and tab the docks of an edge as the layout says, the named tab on top."""
    app = build(LaidOutApp)
    window = app.main_window
    window.resize(1200, 800)
    window.show()
    qapp.processEvents()
    a, b, c, d = (_dock(app, name) for name in "abcd")

    assert {window.dockWidgetArea(dock) for dock in (a, b, c, d)} == {LEFT}
    assert window.dockWidgetArea(_dock(app, "e")) is RIGHT
    assert a.geometry().x() < b.geometry().x()
    assert a.geometry().y() == b.geometry().y()
    assert d.geometry().y() > a.geometry().y()
    assert window.tabifiedDockWidgets(c) == [d]
    assert not d.visibleRegion().isEmpty()


def test_the_centre_is_arranged_like_the_docks(
    qapp: QApplication, build: BuildSession
) -> None:
    """Build the centre as a splitter holding a view and tabs, the named tab current."""
    app = build(LaidOutApp)

    splitter = app.main_window.centralWidget()

    assert isinstance(splitter, QSplitter)
    assert splitter.orientation() is QtNamespace.Orientation.Horizontal
    first, tabs = splitter.widget(0), splitter.widget(1)
    assert first is not None
    assert first.objectName() == "p"
    assert isinstance(tabs, QTabWidget)
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["q", "r"]
    assert tabs.currentIndex() == 1


def test_a_hidden_dock_starts_hidden(qapp: QApplication, build: BuildSession) -> None:
    """Start a dock the layout hides hidden, its Window menu entry unchecked."""
    app = build(LaidOutApp)
    menu = app.main_window.findChild(QModelMenu, WINDOW_MENU)
    assert isinstance(menu, QModelMenu)
    menu.aboutToShow.emit()
    action = menu.findAction("laid-out-session.toggle_dock.e")
    assert isinstance(action, QAction)

    assert _dock(app, "e").isHidden()
    assert not action.isChecked()


def test_without_a_layout_the_window_is_as_before(
    qapp: QApplication, build: BuildSession
) -> None:
    """Tab several central views and a group's docks, as a session without a layout always did."""
    app = build(SeveralCentralApp)

    tabs = app.main_window.centralWidget()

    assert isinstance(tabs, QTabWidget)
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["first", "second"]
    assert app.main_window.tabifiedDockWidgets(_dock(app, "tool")) == [
        _dock(app, "other")
    ]
    assert app.main_window.dockWidgetArea(_dock(app, "tool")) is TOP


def test_a_failed_view_keeps_its_slot_in_the_layout(
    qapp: QApplication, build: BuildSession
) -> None:
    """Put a failed view's placeholder in the place the layout gives it, and keep the saved layout."""
    first = build(FragileLaidOutApp)
    first.main_window.addDockWidget(RIGHT, _dock(first, "panel"))
    first.save_layout()
    first.shutdown()

    second = build(FragileLaidOutApp, {"views": {"fragile": {"fail": True}}})

    assert "fragile" not in second.views
    assert second.main_window.dockWidgetArea(_dock(second, "fragile")) is LEFT
    assert second.main_window.dockWidgetArea(_dock(second, "panel")) is RIGHT


def test_a_view_placed_by_a_property_is_still_attached(
    qapp: QApplication, build: BuildSession
) -> None:
    """Attach a view placed by a deprecated property where it asks, beside a declared layout."""
    app = build(PropertyApp)

    assert app.main_window.dockWidgetArea(_dock(app, "old")) is RIGHT


def test_a_changed_layout_skips_the_saved_one(
    qapp: QApplication, build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Start from a changed layout rather than the arrangement saved under the old one."""
    caplog.set_level(logging.INFO, logger="redsun")
    first = build(LaidOutApp)
    first.main_window.addDockWidget(RIGHT, _dock(first, "a"))
    first.save_layout()
    first.shutdown()

    second = build(LaidOutApp, {"layout": {"regions": {"left": {"tabs": ["a", "b"]}}}})

    assert second.main_window.dockWidgetArea(_dock(second, "a")) is LEFT
    assert "placed differently" in caplog.text


def test_declared_sizes_apply_when_the_window_shows(
    qapp: QApplication, build: BuildSession
) -> None:
    """Give the left edge its share of the window, and each split its weights, once the window shows."""
    app = build(SizedApp)

    _shown(app)

    a, b = _dock(app, "a"), _dock(app, "b")
    splitter = app.main_window.centralWidget()
    assert isinstance(splitter, QSplitter)
    first, second = splitter.sizes()
    assert 250 <= a.width() <= 350
    assert 2.4 <= b.height() / a.height() <= 3.6
    assert 1.6 <= second / first <= 2.4


def test_reset_layout_gives_the_declared_sizes_back(
    qapp: QApplication, build: BuildSession
) -> None:
    """Return a dock the user widened to its declared share when Reset layout runs."""
    app = build(SizedApp)
    _shown(app)
    app.main_window.resizeDocks(
        [_dock(app, "a")], [700], QtNamespace.Orientation.Horizontal
    )

    app.model.commands.execute_command("sized-session.reset_layout")
    qapp.processEvents()

    assert 250 <= _dock(app, "a").width() <= 350


def test_a_restored_layout_keeps_its_sizes(
    qapp: QApplication, build: BuildSession
) -> None:
    """Keep the sizes the user left, the centre's included, over the declared ones."""
    first = build(SizedApp)
    _shown(first)
    first.main_window.resizeDocks(
        [_dock(first, "a")], [500], QtNamespace.Orientation.Horizontal
    )
    splitter = first.main_window.centralWidget()
    assert isinstance(splitter, QSplitter)
    splitter.setSizes([400, 200])
    tabs = splitter.widget(1)
    assert isinstance(tabs, QTabWidget)
    tabs.setCurrentIndex(1)
    first.save_layout()
    first.shutdown()

    second = build(SizedApp)
    _shown(second)

    restored = second.main_window.centralWidget()
    assert isinstance(restored, QSplitter)
    left, right = restored.sizes()
    restored_tabs = restored.widget(1)
    assert isinstance(restored_tabs, QTabWidget)
    assert 420 <= _dock(second, "a").width() <= 580
    assert 1.6 <= left / right <= 2.4
    assert restored_tabs.currentIndex() == 1


def test_a_tab_group_in_a_weighted_edge_keeps_the_edge_narrow(
    qapp: QApplication, build: BuildSession
) -> None:
    """Size an edge whose weighted column holds tabs from the docks on screen, not the tab behind."""
    app = build(TabbedSizesApp)

    _shown(app)

    a, c = _dock(app, "a"), _dock(app, "c")
    assert c.width() < 400
    assert 2.4 <= c.height() / a.height() <= 3.6


def test_a_session_presenting_its_own_way_still_shows_and_saves(
    qapp: QApplication, config_home: Path, build: BuildSession
) -> None:
    """Show and save a session whose own present step skips the layout."""
    app = build(OwnPresentApp)

    _shown(app)
    app.save_layout()

    written = json.loads((config_home / "own-present-session.json").read_text())
    assert app.main_window.isVisible()
    assert written["window.center"] == []


def test_a_damaged_settings_file_starts_from_the_placements(
    qapp: QApplication,
    config_home: Path,
    build: BuildSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Start the docks where their placements say when the saved layout cannot be read, and log why."""
    first = build(LayoutApp)
    first.main_window.addDockWidget(LEFT, _dock(first, "charts"))
    first.save_layout()
    first.shutdown()
    path = config_home / "layout-session.json"
    written = json.loads(path.read_text())
    written["window.state"] = "a"
    path.write_text(json.dumps(written))

    second = build(LayoutApp)

    assert second.main_window.dockWidgetArea(_dock(second, "charts")) is RIGHT
    assert "could not be read" in caplog.text


def test_moving_a_property_placed_view_in_the_layout_skips_the_saved_one(
    qapp: QApplication, build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Start from a layout that moved a view placed by a property, rather than the saved arrangement."""
    caplog.set_level(logging.INFO, logger="redsun")
    first = build(PropertyLaidOutApp)
    first.main_window.addDockWidget(RIGHT, _dock(first, "panel"))
    first.save_layout()
    first.shutdown()

    second = build(
        PropertyLaidOutApp,
        {"layout": {"regions": {"left": {"column": ["old", "panel"]}}}},
    )

    assert second.main_window.dockWidgetArea(_dock(second, "panel")) is LEFT
    assert "placed differently" in caplog.text


def test_attach_refuses_a_layout_naming_a_view_it_was_not_given(
    qapp: QApplication,
) -> None:
    """Refuse a layout naming a view that is not among those to attach, naming it."""
    with pytest.raises(ValueError, match="'ghost'"):
        attach(QMainWindow(), {}, layout=WindowLayout(regions={"left": "ghost"}))


def test_a_second_show_keeps_the_sizes_the_user_set(
    qapp: QApplication, build: BuildSession
) -> None:
    """Keep a dock the user widened when the window is shown again."""
    app = build(SizedApp)
    _shown(app)
    app.main_window.resizeDocks(
        [_dock(app, "a")], [700], QtNamespace.Orientation.Horizontal
    )
    qapp.processEvents()

    _shown(app)

    assert _dock(app, "a").width() > 600
