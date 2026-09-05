"""The Qt frontend: the placements it attaches, and a container to subclass.

Qt is a windowing toolkit, so the placements it understands are window
concepts and are defined here rather than in the core: a docked panel, the
central area, a menu entry, a toolbar entry. Each demands a toolkit type of
the view asking for it, and that pairing is the frontend's alone, which is why
no toolkit type appears in `redsun.experimental.Placement` or in a container.

```python
from redsun.experimental import AsView
from redsun.experimental.session.qt import Dock, QtSession


class ImageView(QWidget):
    placement = Dock("left")


class MyApp(QtSession):
    image: AsView[ImageView]


MyApp().run()
```
"""

from __future__ import annotations

import base64
import logging
import sys
import weakref
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

from app_model import Action, Application
from app_model.backends.qt import QModelMainWindow
from app_model.types import MenuRule
from platformdirs import user_documents_dir
from psygnal._async import clear_async_backend
from psygnal.qt import start_emitting_from_queue
from qtpy.QtCore import QByteArray, QEvent, QObject
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QAction
from qtpy.QtWidgets import (
    QApplication,
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTabWidget,
    QToolBar,
    QWidget,
)

from redsun._hooks import (
    ConfiguresApplication,
    ConfiguresMainView,
    ConfirmsClose,
    CreatesApplication,
    WrapsBuild,
)
from redsun.aio import set_async_backend
from redsun.experimental.session._base import (
    ConfigurationInUse,
    Session,
)
from redsun.experimental.session._frontend import Frontend
from redsun.experimental.session._protocols import DesktopSession
from redsun.experimental.session.qt._actions import read_actions
from redsun.experimental.session.qt._color_scheme import (
    ColorSchemeButton,
    ColorSchemeMode,
)
from redsun.experimental.view._placement import Placement

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from contextlib import AbstractContextManager
    from typing import TypeAlias

    from in_n_out import Store

    from redsun._config import Source
    from redsun.experimental.session._protocols import AttachableComponent

ASK_ON_CLOSE: Final[str] = "ask_on_close"
"""The settings key holding whether the close prompt still appears."""

SAVE_MENU: Final[str] = "redsun/file"
"""The menu a session's own actions join, which a window may show by name."""

__all__ = [
    "Area",
    "Central",
    "Dock",
    "MenuItem",
    "Qt",
    "QtHook",
    "QtSession",
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
    CONFIRM_CLOSE = "confirm_close"


class Qt(Frontend):
    """Qt frontend, attached by `redsun.experimental.session.qt.attach`."""

    requires: ClassVar[Mapping[type[Placement], type]] = {
        Central: QWidget,
        Dock: QWidget,
        MenuItem: QAction,
        ToolBarItem: QAction,
    }


class QtSession(DesktopSession[QMainWindow], Session):
    """Application container whose views are attached to a Qt main window.

    Subclass this rather than `redsun.experimental.Session` to build
    against Qt: it accepts the placements Qt attaches and refuses the rest
    when the declarations are read. Importing it needs the Qt bindings, which
    is why it lives here and not beside the container it extends.

    The base container builds the components; this one puts them in a window.
    Constructing the container touches no toolkit object and reads no file:
    the application, the async backend and the window are all made by `build`.

    ```python
    class MyApp(QtSession):
        image: AsView[ImageView]


    MyApp().run()
    ```
    """

    __slots__ = ("_close_guard", "_main_window", "_model", "_qt_app")

    frontend = Qt
    hook_points: ClassVar[Mapping[str, type]] = {
        QtHook.CREATE_APPLICATION: CreatesApplication,
        QtHook.CONFIGURE_APPLICATION: ConfiguresApplication,
        QtHook.DURING_BUILD: WrapsBuild,
        QtHook.CONFIGURE_MAIN_VIEW: ConfiguresMainView,
        QtHook.CONFIRM_CLOSE: ConfirmsClose,
    }

    def __init__(self, config: Source | Sequence[Source] | None = None) -> None:
        """Prepare an empty container, to be filled by `build`."""
        super().__init__(config)
        self._close_guard: _CloseGuard | None = None
        self._main_window: QModelMainWindow | None = None
        self._model: Application | None = None
        self._qt_app: QApplication | None = None

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
    def app(self) -> QApplication:
        """The toolkit application this session runs on, and keeps alive.

        Nothing else holds one that the session created, and a collected
        ``QApplication`` takes the next widget built with it, so the session
        keeps the reference until it is released.

        Raises
        ------
        RuntimeError
            If read before `build`, which is where it is put in place.
        """
        if self._qt_app is None:
            raise RuntimeError("Call build() before reading the application")
        return self._qt_app

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
        may supply the ``QApplication`` itself. The session's own application
        follows, because the components are built out of its store, and the
        ``actions`` section is registered on it at once, so a hook dressing the
        window finds every command it may put in a menu. The colour scheme is
        asked for before any widget exists to be painted in the wrong one, and
        a ``configure_application`` hook runs last, so one restyling the
        application does so over a scheme already in force. Each of them
        registers how it is given back as it is taken, so ``shutdown`` frees
        the name and the backend without this class defining one.
        """
        hooks = self.hooks
        creator = hooks.get(QtHook.CREATE_APPLICATION)
        if QApplication.instance() is None and isinstance(creator, CreatesApplication):
            qt_app = cast("QApplication", creator.create_application(sys.argv))
        else:
            qt_app = application()
        # the session holds it: nothing else does, and a collected
        # QApplication takes the next widget built with it
        self._qt_app = qt_app
        self.on_release(self._forget_application_object)
        set_async_backend()
        self.on_release(clear_async_backend)

        self._model = Application(self.name)
        self.on_release(self._forget_application)
        # released after the components have shut down and before the
        # application goes, since a widget needs both
        self.on_release(self._destroy_widgets)
        self._register_actions()
        self._register_save_action()

        ColorSchemeMode.from_config(self._configuration()).apply()

        configurer = hooks.get(QtHook.CONFIGURE_APPLICATION)
        if isinstance(configurer, ConfiguresApplication):
            configurer.configure_application(qt_app)

    def _forget_application(self) -> None:
        """Destroy the application by name, freeing the name for the next session."""
        Application.destroy(self.name)
        self._model = None

    def _forget_application_object(self) -> None:
        """Drop the toolkit application, which the session was holding up."""
        self._qt_app = None

    def present(self) -> None:
        """Make the window, put every view where it asks to be, and dress it.

        The colour-scheme toolbar goes on before the views are attached, and
        is added rather than set, so it neither replaces a menu bar nor takes
        a dock area a view asked for.
        """
        window = QModelMainWindow(self.model)
        window.setWindowTitle(self.name)
        self._main_window = window
        # the guard outlives the window only if something holds it, and the
        # window holds an event filter weakly
        self._close_guard = _CloseGuard(self)
        window.installEventFilter(self._close_guard)
        ColorSchemeButton.pin_to(
            window, ColorSchemeMode.from_config(self._configuration())
        )
        attach(window, self.views)
        dresser = self.hooks.get(QtHook.CONFIGURE_MAIN_VIEW)
        if isinstance(dresser, ConfiguresMainView):
            dresser.configure_main_view(window)
        self.restore_layout()

    def restore_layout(self) -> None:
        """Put the window back where this user last left it.

        Runs once every dock exists, since Qt places a dock by object name and
        ignores one it has not seen. A session this user has never run finds
        nothing saved and keeps the layout its views asked for.
        """
        for key, restore in (
            ("window.geometry", self.main_window.restoreGeometry),
            ("window.state", self.main_window.restoreState),
        ):
            saved = self.settings.get(key)
            if isinstance(saved, str):
                restore(QByteArray(base64.b64decode(saved)))

    def save_layout(self) -> None:
        """Remember where this user left the window.

        `run` asks for this as the session ends, so a window that was shown is
        the only one that writes: a session built for a test never displayed
        one, and its geometry means nothing.
        """
        if self._main_window is None:
            return
        self.settings.set("window.geometry", _encoded(self._main_window.saveGeometry()))
        self.settings.set("window.state", _encoded(self._main_window.saveState()))

    def _destroy_widgets(self) -> None:
        """Close and delete the views, then the window that holds them.

        A ``QWidget`` outlives its last Python reference whenever C++ owns it,
        so dropping a component does not end its widget and ``deleteLater`` is
        what does. It is closed first because that is the only way its
        ``closeEvent`` runs: deleting a widget does not send one, and closing
        the window does not send one to a view docked inside it. A component
        written here has ``shutdown`` for its own teardown and needs none of
        this; a view that *is* a third-party widget, wrapping a viewer whose
        cleanup it inherits, has nowhere else for that cleanup to happen.

        The views go in reverse build order, as their own teardowns did, and
        the window after the views it docks. Reading it afterwards
        reports an unbuilt session rather than handing back a wrapper whose
        widget is gone. A reference taken before the shutdown is left wrapping
        a destroyed widget, and using it raises ``RuntimeError``.
        """
        for view in reversed(list(self.views.values())):
            if isinstance(view, QWidget):
                view.close()
                view.deleteLater()
        if self._main_window is not None:
            self._main_window.close()
            self._main_window.deleteLater()
            self._main_window = None
        if self._qt_app is not None:
            # deleteLater only posts the deletion, and a session shut down
            # with no loop running would never reach the pass that carries
            # it out
            self._qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def _confirm_close(self) -> bool:
        """Return whether the session may close, asking about unsaved changes.

        Closing the window is what calls this, so the title bar, `close()` and
        quitting the application all reach it. A hook installed at
        `QtHook.CONFIRM_CLOSE` answers in place of the prompt.

        Without such a hook, a session that no component asks to be written
        differently from closes without a word, and so does one whose user has
        ticked "don't ask again". Otherwise the prompt offers Save, Discard and
        Cancel.

        Underscored because a hook point's key is the attribute a hook is
        declared under, which a public method of that name would collide with.
        """
        confirmer = self.hooks.get(QtHook.CONFIRM_CLOSE)
        if isinstance(confirmer, ConfirmsClose):
            return confirmer.confirm_close()
        if not self.has_changes() or not self.settings.get(ASK_ON_CLOSE, True):
            return True
        return self._ask_about_changes()

    def _ask_about_changes(self) -> bool:
        """Put the unsaved-changes question to the user, and act on the answer.

        Saving is the save action, so a cancelled save dialog leaves the
        session open rather than closing it with the changes dropped.
        """
        prompt = QMessageBox(self._main_window)
        prompt.setWindowTitle("Unsaved changes")
        prompt.setText(f"'{self.name}' has changes no file holds yet.")
        prompt.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        prompt.setDefaultButton(QMessageBox.StandardButton.Save)
        again = QCheckBox("Don't ask again")
        prompt.setCheckBox(again)

        answer = prompt.exec()
        if again.isChecked():
            self.settings.set(ASK_ON_CLOSE, False)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Discard:
            return True
        return self._save_configuration()

    def _register_save_action(self) -> None:
        """Register the action writing the session out to a file the user picks.

        It joins `SAVE_MENU`, so a window showing that menu by name offers it
        without the session naming a widget.
        """
        action = Action(
            id=f"{self.name}.save_configuration",
            title="Save configuration as...",
            callback=self._save_configuration,
            menus=[MenuRule(id=SAVE_MENU)],
        )
        self.on_release(self.model.register_action(action))

    def _save_configuration(self) -> bool:
        """Ask where to write the session, write it there, and say whether it went.

        The dialog says comments are not kept, the file being written rather
        than edited. A path the session was built from is refused after the
        dialog has accepted it, since only the session knows which files those
        are and what else reads them.
        """
        path, _ = QFileDialog.getSaveFileName(
            self._main_window,
            "Save configuration as (comments are not kept)",
            user_documents_dir(),
            "YAML (*.yaml *.yml)",
        )
        if not path:
            return False
        try:
            self.write(path)
        except ConfigurationInUse as reason:
            QMessageBox.warning(self._main_window, "Configuration in use", str(reason))
            return False
        return True

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
        self.on_release(self.model.register_actions(actions))
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
            return hook.during_build(self.app)
        return nullcontext(self._report)

    def run(self) -> NoReturn:
        """Build, show the window, and hand over to the event loop."""
        self.build()
        self.on_release(self.save_layout)
        self.app.aboutToQuit.connect(self.shutdown)
        start_emitting_from_queue()
        self.main_window.show()
        sys.exit(self.app.exec())


class _CloseGuard(QObject):
    """Puts a window's close to the session, which may refuse it."""

    def __init__(self, session: QtSession) -> None:
        super().__init__()
        self._session = weakref.ref(session)

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        """Refuse a close the session does not confirm."""
        session = self._session()
        if obj is None or event is None:
            return False
        if (
            event.type() == QEvent.Type.Close
            and session is not None
            and not session._confirm_close()
        ):
            event.ignore()
            return True
        return super().eventFilter(obj, event)


def _encoded(state: QByteArray) -> str:
    """Return *state* as text, the settings file holding JSON rather than bytes."""
    return base64.b64encode(state.data()).decode("ascii")


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
    # Qt matches a dock to its saved place by object name, and drops one that
    # has none, so the component's declared name is what carries the layout
    dock = QDockWidget(name, window)
    dock.setObjectName(name)
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
