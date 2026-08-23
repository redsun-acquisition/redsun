"""The Qt frontend: the placements it attaches, and a container to subclass.

Qt is a windowing toolkit, so the placements it understands are window
concepts and are defined here rather than in the core: a docked panel, the
central area, a menu entry, a toolbar entry. Each demands a toolkit type of
the view asking for it, and that pairing is the frontend's alone, which is why
no toolkit type appears in `redsun.experimental.Placement` or in a container.

```python
from redsun.experimental import AsView
from redsun.experimental.qt import Dock, QtAppContainer


class ImageView(QWidget):
    placement = Dock("left")


class MyApp(QtAppContainer):
    image: AsView[ImageView]


MyApp().run()
```
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    ClassVar,
    Final,
    Literal,
    NoReturn,
    Self,
    cast,
    overload,
)

# psygnal re-exports get/set_async_backend at the top level but not this one
from psygnal._async import clear_async_backend
from psygnal.qt import start_emitting_from_queue
from qtpy.QtCore import Qt as QtNamespace

# qtpy reaches QAction through a plain named import, which strict mode counts
# as no export at all and resolves to Any
from qtpy.QtGui import QAction  # type: ignore[attr-defined]
from qtpy.QtWidgets import (
    QApplication,
    QDockWidget,
    QMainWindow,
    QMenu,
    QTabWidget,
    QToolBar,
    QWidget,
)

from redsun.aio import set_async_backend
from redsun.experimental._container import AppContainer
from redsun.experimental._frontend import Frontend
from redsun.experimental._placement import Placement

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path
    from typing import Any, TypeAlias

    from redsun.experimental._protocols import PView

__all__ = [
    "REQUIRES",
    "Area",
    "Central",
    "Dock",
    "MenuItem",
    "Qt",
    "QtAppContainer",
    "ToolBarItem",
    "attach",
]

Area: TypeAlias = Literal["left", "right", "top", "bottom"]


@dataclass(frozen=True)
class Dock(Placement):
    """A panel against one edge of the window."""

    area: Area


@dataclass(frozen=True)
class Central(Placement):
    """The main area of the window, shared when more than one view asks."""


@dataclass(frozen=True)
class MenuItem(Placement):
    """An entry in a named menu of the menu bar."""

    menu: str


@dataclass(frozen=True)
class ToolBarItem(Placement):
    """An entry in a named toolbar."""

    toolbar: str


REQUIRES: Final[dict[type[Placement], type[QWidget | QAction]]] = {
    Central: QWidget,
    Dock: QWidget,
    MenuItem: QAction,
    ToolBarItem: QAction,
}
"""The toolkit type each placement demands of the view asking for it."""


class Qt(Frontend):
    """Qt frontend, attached by `redsun.experimental.qt.attach`."""

    placements: ClassVar[frozenset[type[Placement]]] = frozenset(REQUIRES)


class QtAppContainer(AppContainer):
    """Application container whose views are attached to a Qt main window.

    Subclass this rather than `redsun.experimental.AppContainer` to build
    against Qt: it accepts the placements Qt attaches and refuses the rest
    when the declarations are read. Importing it needs the Qt bindings, which
    is why it lives here and not beside the container it extends.

    The base container builds the components; this one puts them in a window.
    Everything the toolkit needs in place before a component exists is built in
    ``__init__``, so an override of `build` or `shutdown` calls ``super()``
    first and does its own work afterwards.

    ```python
    class MyApp(QtAppContainer):
        image: AsView[ImageView]


    MyApp().run()
    ```
    """

    __slots__ = ("_main_window", "_qt_app")

    frontend = Qt

    def __init__(self, config: str | Path | Mapping[str, Any] | None = None) -> None:
        """Put the toolkit in place, before any component can need it.

        A ``QApplication`` has to exist before any widget is constructed and
        the async backend before any coroutine slot is connected, so neither
        can wait for `build`. The window is empty until then.
        """
        super().__init__(config)
        self._qt_app = cast(
            "QApplication", QApplication.instance() or QApplication(sys.argv)
        )
        set_async_backend()
        self._main_window = QMainWindow()

    @property
    def main_window(self) -> QMainWindow:
        """The window the views are attached to, empty until `build`."""
        return self._main_window

    def build(self) -> Self:
        """Build the components, then attach the views to the main window.

        Refusing a second build is the base container's to do, so a call that
        it turns away attaches nothing rather than filling the window twice.
        """
        already = self.is_built
        super().build()
        if not already:
            self._main_window.setWindowTitle(self.virtual_container.session)
            attach(self._main_window, self.views)
        return self

    def shutdown(self) -> None:
        """Tear the application down, then the async backend it ran on."""
        super().shutdown()
        clear_async_backend()

    def run(self) -> NoReturn:
        """Build, show the window, and hand over to the event loop."""
        self.build()
        self._qt_app.aboutToQuit.connect(self.shutdown)
        start_emitting_from_queue()
        self._main_window.show()
        sys.exit(self._qt_app.exec())


_AREAS: Final[dict[Area, QtNamespace.DockWidgetArea]] = {
    "left": QtNamespace.DockWidgetArea.LeftDockWidgetArea,
    "right": QtNamespace.DockWidgetArea.RightDockWidgetArea,
    "top": QtNamespace.DockWidgetArea.TopDockWidgetArea,
    "bottom": QtNamespace.DockWidgetArea.BottomDockWidgetArea,
}


def attach(window: QMainWindow, views: Mapping[str, PView]) -> None:
    """Attach every view of *views* to *window* where it asks to be.

    Raises
    ------
    TypeError
        If a view asks for a placement Qt does not attach, or is not the
        toolkit type that placement demands.
    """
    central: dict[str, QWidget] = {}
    for name, view in views.items():
        placement = view.placement
        match placement:
            case Central():
                central[name] = _checked(name, view, placement)
            case Dock():
                _dock(window, name, _checked(name, view, placement), placement)
            case MenuItem():
                _menu(window, _checked(name, view, placement), placement)
            case ToolBarItem():
                _toolbar(window, _checked(name, view, placement), placement)
            case _:
                raise TypeError(
                    f"view {name!r} asks to be attached as "
                    f"{type(placement).__name__!r}, which Qt does not attach. "
                    "It attaches: "
                    + ", ".join(sorted(p.__name__ for p in REQUIRES))
                    + "."
                )
    _center(window, central)


@overload
def _checked(name: str, view: PView, placement: Central | Dock) -> QWidget: ...


@overload
def _checked(name: str, view: PView, placement: MenuItem | ToolBarItem) -> QAction: ...


def _checked(name: str, view: PView, placement: Placement) -> QWidget | QAction:
    """Return *view* as the toolkit type *placement* demands, named after it.

    Raises
    ------
    TypeError
        If the view is not that type.
    """
    required = REQUIRES[type(placement)]
    if not isinstance(view, required):
        raise TypeError(
            f"view {name!r} asks to be attached as {type(placement).__name__!r}, "
            f"which needs a {required.__name__}, but {type(view).__name__} is "
            "not one"
        )
    view.setObjectName(name)
    return view


def _dock(window: QMainWindow, name: str, widget: QWidget, placement: Dock) -> None:
    dock = QDockWidget(name, window)
    dock.setWidget(widget)
    window.addDockWidget(_AREAS[placement.area], dock)


def _menu(window: QMainWindow, action: QAction, placement: MenuItem) -> None:
    bar = window.menuBar()
    if bar is None:
        raise TypeError(f"{type(window).__name__} has no menu bar to add a menu to")
    for existing in bar.actions():
        menu = existing.menu()
        if menu is not None and menu.title() == placement.menu:
            menu.addAction(action)
            return
    created = QMenu(placement.menu, window)
    created.addAction(action)
    bar.addMenu(created)


def _toolbar(window: QMainWindow, action: QAction, placement: ToolBarItem) -> None:
    existing = window.findChildren(QToolBar, placement.toolbar)
    if existing:
        existing[0].addAction(action)
        return
    bar = QToolBar(placement.toolbar, window)
    bar.setObjectName(placement.toolbar)
    window.addToolBar(bar)
    bar.addAction(action)


def _center(window: QMainWindow, central: dict[str, QWidget]) -> None:
    """Give the central area to the one view asking, or tab them when several do."""
    if not central:
        return
    if len(central) == 1:
        window.setCentralWidget(next(iter(central.values())))
        return
    tabs = QTabWidget()
    for name, widget in central.items():
        tabs.addTab(widget, name)
    window.setCentralWidget(tabs)
