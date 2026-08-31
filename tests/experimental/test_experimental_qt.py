"""Tests for attaching experimental views to a Qt main window."""

from __future__ import annotations

from typing import Any

import pytest

# qtpy reaches QAction through a plain named import, which strict mode counts
# as no export at all and resolves to Any
from qtpy.QtGui import QAction
from qtpy.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QMenu,
    QTabWidget,
    QToolBar,
    QWidget,
)

from redsun.experimental import AppContainer, AsView, Placement, PView
from redsun.experimental.containers.qt import (
    Central,
    Dock,
    MenuItem,
    Qt,
    QtAppContainer,
    ToolBarItem,
    attach,
)

pytestmark = pytest.mark.qt


class Panel(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name


class Canvas(QWidget):
    placement: Placement = Central()

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name


class Other(QWidget):
    placement: Placement = Central()

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name


class Save(QAction):
    placement: Placement = MenuItem("File")

    def __init__(self, name: str, /) -> None:
        super().__init__(name)
        self.name = name


class Open(QAction):
    placement: Placement = MenuItem("File")

    def __init__(self, name: str, /) -> None:
        super().__init__(name)
        self.name = name


class Acquire(QAction):
    placement: Placement = ToolBarItem("Plans")

    def __init__(self, name: str, /) -> None:
        super().__init__(name)
        self.name = name


class NotAWidget:
    placement: Placement = Dock("left")

    def __init__(self, name: str, /) -> None:
        self.name = name


class QtApp(QtAppContainer):
    __slots__ = ()

    panel: AsView[Panel]
    canvas: AsView[Canvas]
    save: AsView[Save]
    acquire: AsView[Acquire]


@pytest.fixture
def window(qapp: Any) -> QMainWindow:
    return QMainWindow()


def test_the_container_builds_its_own_window(qapp: Any) -> None:
    """The base container builds the components; this one arranges them."""
    app = QtApp().build()
    try:
        window = app.main_window
        assert window.windowTitle() == "Redsun"
        docks = window.findChildren(QDockWidget)
        assert [_widget(d).objectName() for d in docks] == ["panel"]
        central = window.centralWidget()
        assert central is not None
        assert central.objectName() == "canvas"
        assert app.build().main_window is window
    finally:
        app.shutdown()


def test_the_window_exists_before_the_build_and_is_kept(qapp: Any) -> None:
    """The toolkit is in place from construction; only its content waits."""
    app = QtApp()
    window = app.main_window
    assert window.findChildren(QDockWidget) == []
    try:
        assert app.build().main_window is window
    finally:
        app.shutdown()


def test_the_configuration_names_the_container(qapp: Any) -> None:
    """A session naming Qt comes up on the Qt container without a class."""
    app = AppContainer.from_config({"frontend": "pyqt", "session": "from-file"})
    assert isinstance(app, QtAppContainer)
    assert app.frontend is Qt
    try:
        assert app.build().main_window.windowTitle() == "from-file"
    finally:
        app.shutdown()


def test_every_placement_lands_where_it_asked(window: QMainWindow) -> None:
    """One pass over the views fills docks, the centre, a menu and a toolbar."""
    app = QtApp().build()
    try:
        attach(window, dict(app.views))
    finally:
        app.shutdown()

    docks = window.findChildren(QDockWidget)
    assert [_widget(d).objectName() for d in docks] == ["panel"]
    central = window.centralWidget()
    assert central is not None
    assert central.objectName() == "canvas"

    menus = _menus(window)
    assert [m.title() for m in menus] == ["File"]
    assert [a.objectName() for a in menus[0].actions()] == ["save"]

    toolbars = window.findChildren(QToolBar)
    assert [t.objectName() for t in toolbars] == ["Plans"]
    assert [a.objectName() for a in toolbars[0].actions()] == ["acquire"]


def test_one_menu_holds_every_entry_asking_for_it(window: QMainWindow) -> None:
    """The menu is created once and found again, not created per entry."""
    # a QAction is not reparented by addAction, so the caller keeps it alive
    views: dict[str, PView] = {"save": Save("save"), "open": Open("open")}
    attach(window, views)

    menus = _menus(window)
    assert len(menus) == 1
    assert [a.objectName() for a in menus[0].actions()] == ["save", "open"]


def test_several_central_views_share_the_area_as_tabs(window: QMainWindow) -> None:
    attach(window, {"canvas": Canvas("canvas"), "other": Other("other")})

    tabs = window.centralWidget()
    assert isinstance(tabs, QTabWidget)
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["canvas", "other"]


def test_a_view_of_the_wrong_toolkit_type_is_refused(window: QMainWindow) -> None:
    """The placement decides what the view must be, and only Qt knows that."""
    with pytest.raises(TypeError, match="needs a QWidget, but NotAWidget is not one"):
        attach(window, {"stray": NotAWidget("stray")})


def test_a_view_of_the_wrong_toolkit_type_is_refused_before_it_is_built(
    qapp: Any,
) -> None:
    """Qt's requirement table is read with the declarations, not at attach."""

    class Wrong(QtAppContainer):
        __slots__ = ()

        stray: AsView[NotAWidget]

    with pytest.raises(
        TypeError, match=r"Wrong\.stray .* needs a QWidget, but NotAWidget is not one"
    ):
        Wrong().build()


def _menus(window: QMainWindow) -> list[QMenu]:
    return window.findChildren(QMenu)


def _widget(dock: QDockWidget) -> QWidget:
    inner = dock.widget()
    assert inner is not None
    return inner
