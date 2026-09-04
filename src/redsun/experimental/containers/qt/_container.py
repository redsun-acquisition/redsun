"""The Qt frontend: the placements it attaches, and a container to subclass.

Qt is a windowing toolkit, so the placements it understands are window
concepts and are defined here rather than in the core: a docked panel, the
central area, a menu entry, a toolbar entry. Each demands a toolkit type of
the view asking for it, and that pairing is the frontend's alone, which is why
no toolkit type appears in `redsun.experimental.Placement` or in a container.

```python
from redsun.experimental import AsView
from redsun.experimental.containers.qt import Dock, QtAppContainer


class ImageView(QWidget):
    placement = Dock("left")


class MyApp(QtAppContainer):
    image: AsView[ImageView]


MyApp().run()
```
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping  # noqa: TC003
from contextlib import nullcontext
from dataclasses import dataclass
from enum import StrEnum
from typing import (
    TYPE_CHECKING,
    ClassVar,
    Final,
    Literal,
    NoReturn,
    TypeVar,
    cast,
)

from app_model import Application
from app_model.backends.qt import QModelMainWindow
from psygnal._async import clear_async_backend
from psygnal.qt import start_emitting_from_queue
from qtpy.QtCore import QObject
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QAction
from qtpy.QtWidgets import (
    QApplication,
    QDockWidget,
    QMainWindow,
    QMenu,
    QTabWidget,
    QToolBar,
    QWidget,
)

from redsun._hooks import (
    ConfiguresApplication,
    ConfiguresMainView,
    CreatesApplication,
    WrapsBuild,
)
from redsun.aio import set_async_backend
from redsun.experimental.containers._frontend import Frontend
from redsun.experimental.containers._protocols import DesktopSession
from redsun.experimental.containers.container import AppContainer
from redsun.experimental.containers.qt._actions import read_actions
from redsun.experimental.view._placement import Placement

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from contextlib import AbstractContextManager
    from typing import TypeAlias

    from in_n_out import Store

    from redsun._config import Source
    from redsun.experimental.containers._protocols import AttachableComponent

__all__ = [
    "Area",
    "Central",
    "Dock",
    "MenuItem",
    "Qt",
    "QtAppContainer",
    "QtHook",
    "ToolBarItem",
    "attach",
]

logger = logging.getLogger("redsun")

Area: TypeAlias = Literal["left", "right", "top", "bottom"]

T = TypeVar("T", bound=QObject)


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


class QtHook(StrEnum):
    """The points a Qt session calls a hook at.

    A member is its own string, so the attribute name declaring a hook, the key
    of a ``hooks`` configuration entry and a member here are the same thing
    said three ways.
    """

    CREATE_APPLICATION = "create_application"
    CONFIGURE_APPLICATION = "configure_application"
    DURING_BUILD = "during_build"
    CONFIGURE_MAIN_VIEW = "configure_main_view"


class Qt(Frontend):
    """Qt frontend, attached by `redsun.experimental.containers.qt.attach`."""

    requires: ClassVar[Mapping[type[Placement], type]] = {
        Central: QWidget,
        Dock: QWidget,
        MenuItem: QAction,
        ToolBarItem: QAction,
    }


class QtAppContainer(DesktopSession[QMainWindow], AppContainer):
    """Application container whose views are attached to a Qt main window.

    Subclass this rather than `redsun.experimental.AppContainer` to build
    against Qt: it accepts the placements Qt attaches and refuses the rest
    when the declarations are read. Importing it needs the Qt bindings, which
    is why it lives here and not beside the container it extends.

    The base container builds the components; this one puts them in a window.
    Constructing the container touches no toolkit object and reads no file:
    the application, the async backend and the window are all made by `build`.

    ```python
    class MyApp(QtAppContainer):
        image: AsView[ImageView]


    MyApp().run()
    ```
    """

    __slots__ = ("_main_window", "_model")

    frontend = Qt
    hook_points: ClassVar[Mapping[str, type]] = {
        QtHook.CREATE_APPLICATION: CreatesApplication,
        QtHook.CONFIGURE_APPLICATION: ConfiguresApplication,
        QtHook.DURING_BUILD: WrapsBuild,
        QtHook.CONFIGURE_MAIN_VIEW: ConfiguresMainView,
    }

    def __init__(self, config: Source | Sequence[Source] | None = None) -> None:
        """Prepare an empty container, to be filled by `build`."""
        super().__init__(config)
        self._main_window: QModelMainWindow | None = None
        self._model: Application | None = None

    @property
    def main_window(self) -> QModelMainWindow:
        """The window the views are attached to.

        It is built against `model`, so a menu bar or a toolbar filled from
        that application's registries can be asked for on it.

        Raises
        ------
        RuntimeError
            If read before `build`, which is where it is created.
        """
        if self._main_window is None:
            raise RuntimeError("Call build() before reading the main window")
        return self._main_window

    @property
    def model(self) -> Application:
        """The application this session's commands and menus are registered on.

        Raises
        ------
        RuntimeError
            If read before `build`, which is where it is created.
        """
        if self._model is None:
            raise RuntimeError("Call build() before reading the application")
        return self._model

    def start_runtime(self) -> None:
        """Put the toolkit in place, before the first component is built.

        A ``QApplication`` has to exist before any widget is constructed and
        the async backend before any coroutine slot is connected, so both are
        made here. The hooks were resolved by the step before this one, so one
        may supply the ``QApplication`` itself. The application follows,
        because the components are built out of its store, and the ``actions``
        section is registered on it at once, so a hook dressing the window
        finds every command it may put in a menu. Each of them registers how
        it is given back as it is taken, so ``shutdown`` frees the name and
        the backend without this class defining one.
        """
        hooks = self.hooks
        creator = hooks.get(QtHook.CREATE_APPLICATION)
        if QApplication.instance() is None and isinstance(creator, CreatesApplication):
            qt_app = cast("QApplication", creator.create_application(sys.argv))
        else:
            qt_app = application()
        set_async_backend()
        self.on_release(clear_async_backend)

        configurer = hooks.get(QtHook.CONFIGURE_APPLICATION)
        if isinstance(configurer, ConfiguresApplication):
            configurer.configure_application(qt_app)

        self._model = Application(self.name)
        self.on_release(self._forget_application)
        self._register_actions()

    def _forget_application(self) -> None:
        """Destroy the application by name, freeing the name for the next session."""
        Application.destroy(self.name)
        self._model = None

    def present(self) -> None:
        """Make the window, put every view where it asks to be, and dress it."""
        window = QModelMainWindow(self.model)
        window.setWindowTitle(self.name)
        self._main_window = window
        self.on_release(self._forget_window)
        attach(window, self.views)
        dresser = self.hooks.get(QtHook.CONFIGURE_MAIN_VIEW)
        if isinstance(dresser, ConfiguresMainView):
            dresser.configure_main_view(window)

    def _forget_window(self) -> None:
        """Drop the window, so reading it reports an unbuilt session again."""
        self._main_window = None

    def _register_actions(self) -> None:
        """Register what the ``actions`` section declares on the application.

        The disposer goes on the virtual container, which is released before
        the application is destroyed, so a second session under the same name
        starts against a registry holding nothing of the first.

        Raises
        ------
        ActionError
            If the section is not a list, or an entry is not an action.
        """
        actions = read_actions(
            self._configuration().get("actions"), type(self).__name__
        )
        if not actions:
            return
        self.virtual_container.on_release(self.model.register_actions(actions))
        logger.debug(
            "Registered %d action(s) on %r: %s",
            len(actions),
            self.name,
            ", ".join(action.id for action in actions),
        )

    def make_store(self) -> Store:
        """Return the application's store, which is the session's too.

        Sharing it is what lets a command registered on the application be
        filled from the components this session built.
        """
        return self.model.injection_store

    def open_span(self) -> AbstractContextManager[Callable[[str], None]]:
        """Open the span a `QtHook.DURING_BUILD` hook wraps the build in.

        Without one, reporting stays where it was and nothing brackets the
        build. The ``runtime`` step has run by now, so the ``QApplication`` a
        hook is handed exists.
        """
        hook = self.hooks.get(QtHook.DURING_BUILD)
        if isinstance(hook, WrapsBuild):
            return hook.during_build(application())
        return nullcontext(self._report)

    def run(self) -> NoReturn:
        """Build, show the window, and hand over to the event loop."""
        self.build()
        qt_app = application()
        qt_app.aboutToQuit.connect(self.shutdown)
        start_emitting_from_queue()
        self.main_window.show()
        sys.exit(qt_app.exec())


def application() -> QApplication:
    """Return the running application, or start the one this session needs."""
    return cast("QApplication", QApplication.instance() or QApplication(sys.argv))


_AREAS: Final[dict[Area, QtNamespace.DockWidgetArea]] = {
    "left": QtNamespace.DockWidgetArea.LeftDockWidgetArea,
    "right": QtNamespace.DockWidgetArea.RightDockWidgetArea,
    "top": QtNamespace.DockWidgetArea.TopDockWidgetArea,
    "bottom": QtNamespace.DockWidgetArea.BottomDockWidgetArea,
}


def attach(window: QMainWindow, views: Mapping[str, AttachableComponent]) -> None:
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
                central[name] = _named(name, view, placement, QWidget)
            case Dock():
                _dock(window, name, _named(name, view, placement, QWidget), placement)
            case MenuItem():
                _menu(window, _named(name, view, placement, QAction), placement)
            case ToolBarItem():
                _toolbar(window, _named(name, view, placement, QAction), placement)
            case _:
                raise TypeError(
                    f"view {name!r} asks to be attached as "
                    f"{type(placement).__name__!r}, which Qt does not attach. "
                    "It attaches: "
                    + ", ".join(sorted(p.__name__ for p in Qt.requires))
                    + "."
                )
    _center(window, central)


# taken as 'object' rather than 'AttachableComponent': narrowing a protocol
# against a type variable leaves mypy nothing it can name, and it yields Never
def _named(name: str, view: object, placement: Placement, required: type[T]) -> T:
    """Return *view* as *required*, named after *name* so it can be found again.

    Raises
    ------
    TypeError
        If the view is not that type.
    """
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
    # found by object name rather than through QAction.menu(), which the two
    # bindings type differently: QMenu under pyqt6, QObject under pyside6
    existing = window.findChildren(QMenu, placement.menu)
    if existing:
        existing[0].addAction(action)
        return
    created = QMenu(placement.menu, window)
    created.setObjectName(placement.menu)
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
