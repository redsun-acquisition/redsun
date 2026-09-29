"""The Qt frontend: the placements it attaches, and a container to subclass.

The placements Qt attaches are defined here: a docked panel, the central
area, a menu entry, a toolbar entry. Each demands a toolkit type of the view
asking for it.

```python
from redsun import AsView
from redsun.qt import Dock, QtSession


class ImageView(QWidget):
    placement = Dock("left")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)


class MyApp(QtSession):
    image: AsView[ImageView]


MyApp().run()
```
"""

from __future__ import annotations

import base64
import inspect
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
    get_args,
)

from app_model import Action, Application
from app_model.backends.qt import QModelMainWindow
from app_model.types import MenuRule
from platformdirs import user_documents_dir
from psygnal import emit_queued
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

from redsun.errors import ConfigurationInUse
from redsun.view import Placement

from .._hooks import (
    ConfiguresApplication,
    ConfiguresMainView,
    ConfirmsClose,
    CreatesApplication,
    WrapsBuild,
)
from ..session._base import Session
from ..session._declarations import Layer
from ..session._factories import resolved
from ..session._frontend import Frontend
from ..session._protocols import DesktopSession
from ..view.qt._failed import FailedView, FailuresButton
from ._actions import read_actions
from ._color_scheme import (
    ColorSchemeButton,
    ColorSchemeMode,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from contextlib import AbstractContextManager
    from types import TracebackType
    from typing import TypeAlias

    from in_n_out import Store

    from .._config import Source
    from ..ports import SlotThread
    from ..session._declarations import Declaration
    from ..session._protocols import AttachableComponent, NamedComponent

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
    """A panel against one edge of the window.

    Raises
    ------
    ValueError
        If `area` names no edge of the window.
    """

    area: Area
    """Edge the panel sits against."""

    def __post_init__(self) -> None:
        if self.area not in get_args(Area):
            raise ValueError(
                f"Dock({self.area!r}) names no edge of the window; "
                f"use one of {', '.join(get_args(Area))}"
            )


@dataclass(frozen=True)
class Central(Placement):
    """The main area of the window, shared when more than one view asks."""


@dataclass(frozen=True)
class MenuItem(Placement):
    """An entry in a named menu of the menu bar."""

    menu: str
    """Name of the menu."""


@dataclass(frozen=True)
class ToolBarItem(Placement):
    """An entry in a named toolbar."""

    toolbar: str
    """Name of the toolbar."""


class QtHook(StrEnum):
    """The points a Qt session calls a hook at.

    A member is its own string, so the attribute name declaring a hook, the key
    of a `hooks` configuration entry and a member here are the same thing
    said three ways.
    """

    CREATE_APPLICATION = "create_application"
    """Makes the `QApplication` from the command-line arguments, when none exists yet."""

    CONFIGURE_APPLICATION = "configure_application"
    """Receives the `QApplication` before any view is made."""

    DURING_BUILD = "during_build"
    """Receives the `QApplication` and wraps the build steps."""

    CONFIGURE_MAIN_VIEW = "configure_main_view"
    """Receives the main window once it is made, before it is shown."""

    CONFIRM_CLOSE = "confirm_close"
    """Answers whether the window may close."""


class Qt(Frontend):
    """Qt frontend, attached by `redsun.qt.attach`."""

    requires: ClassVar[Mapping[type[Placement], type]] = {
        Central: QWidget,
        Dock: QWidget,
        MenuItem: QAction,
        ToolBarItem: QAction,
    }

    @classmethod
    def check_view(cls, view: type, where: str) -> None:
        """Refuse a view whose constructor does not start `(name: str, parent: QWidget`.

        The session passes both by keyword, so neither may sit after a `/`,
        and neither may sit after a `*`, so a missing `parent` shows in the
        first line of the signature.

        Raises
        ------
        TypeError
            If the constructor starts any other way.
        """
        params = resolved(view, f"the constructor of {view.__qualname__}").parameters
        leading = [
            (param.name, param.kind, param.annotation)
            for param in list(params.values())[:2]
        ]
        if leading == [
            ("name", inspect.Parameter.POSITIONAL_OR_KEYWORD, str),
            ("parent", inspect.Parameter.POSITIONAL_OR_KEYWORD, QWidget),
        ]:
            return
        raise TypeError(
            f"{where} is declared as a view, but {view.__name__}'s constructor "
            "does not start with '(name: str, parent: QWidget)', which the Qt "
            "session passes to every view; neither may sit after a '/' or a '*'"
        )

    @classmethod
    def thread_of(cls, consumer: object) -> SlotThread:
        """Run a widget's slots on the main thread, the only one it may be used from."""
        return "main" if isinstance(consumer, QWidget) else None


class QtSession(DesktopSession[QMainWindow], Session):
    """Application container whose views are attached to a Qt main window.

    Subclass this rather than `redsun.Session` to build
    against Qt: it accepts the placements Qt attaches and refuses the rest
    when the declarations are read. Importing it needs the Qt bindings.

    The base container builds the components; this one puts them in a window.
    Constructing the container touches no toolkit object and reads no file:
    the application, the async backend and the window are all made by `build`.

    ```python
    class MyApp(QtSession):
        image: AsView[ImageView]


    MyApp().run()
    ```
    """

    __slots__ = (
        "_close_guard",
        "_main_window",
        "_model",
        "_qt_app",
        "_window_widgets",
    )

    frontend = Qt
    hook_points: ClassVar[Mapping[str, type]] = {
        QtHook.CREATE_APPLICATION: CreatesApplication,
        QtHook.CONFIGURE_APPLICATION: ConfiguresApplication,
        QtHook.DURING_BUILD: WrapsBuild,
        QtHook.CONFIGURE_MAIN_VIEW: ConfiguresMainView,
        QtHook.CONFIRM_CLOSE: ConfirmsClose,
    }

    def __init__(
        self,
        config: Source | Sequence[Source] | None = None,
        *,
        log_level: int | str | None = None,
    ) -> None:
        """Prepare an empty container, to be filled by `build`."""
        super().__init__(config, log_level=log_level)
        self._close_guard: CloseGuard | None = None
        self._main_window: QModelMainWindow | None = None
        self._model: Application | None = None
        self._qt_app: QApplication | None = None
        self._window_widgets: set[QWidget] = set()

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
    def view_arguments(self) -> Mapping[str, object]:
        """The main window, as every view's `parent`."""
        return {"parent": self.main_window}

    @property
    def app(self) -> QApplication:
        """The toolkit application this session runs on, and keeps alive.

        The session keeps a reference to one it created until it is released.

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

        A `QApplication` has to exist before any widget is constructed, so it
        is made here. The hooks were resolved by the step before this one, so one
        may supply the `QApplication` itself. The session's own application
        follows, because the components are built out of its store, and the
        `actions` section is registered on it at once, so a hook dressing the
        window finds every command it may put in a menu. The window comes next,
        since every view is built as its child. The colour scheme is
        asked for before any widget exists to be painted in the wrong one, and
        a `configure_application` hook runs last, so one restyling the
        application does so over a scheme already in force. Each of them
        registers how it is given back as it is taken, so `shutdown` frees
        the name without this class defining one.
        """
        super().start_runtime()
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

        self._model = Application(self.name)
        self.on_release(self._forget_application)
        # released after the components have shut down and before the
        # application goes, since a widget needs both
        self.on_release(self._destroy_widgets)
        self._register_actions()
        self._register_save_action()
        window = QModelMainWindow(self._model)
        window.setWindowTitle(self.name)
        self._main_window = window

        ColorSchemeMode.from_config(self._configuration().color_scheme).apply()

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

    def build_views(self) -> None:
        """Build the views as children of the main window.

        A view that fails after handing itself to the window as a child would
        be shown with it, so what it left behind is deleted.
        """
        self._window_widgets = self._direct_widgets()
        super().build_views()

    def _on_built(self, declaration: Declaration, instance: NamedComponent) -> None:
        super()._on_built(declaration, instance)
        if declaration.kind is Layer.VIEW:
            self._window_widgets = self._direct_widgets()

    def _skip(self, declaration: Declaration, reason: BaseException) -> None:
        super()._skip(declaration, reason)
        if declaration.kind is not Layer.VIEW or self._main_window is None:
            return
        for widget in self._direct_widgets() - self._window_widgets:
            widget.hide()
            widget.deleteLater()

    def _direct_widgets(self) -> set[QWidget]:
        return set(
            self.main_window.findChildren(
                QWidget, options=QtNamespace.FindChildOption.FindDirectChildrenOnly
            )
        )

    def present(self) -> None:
        """Make the window, put every view where it asks to be, and dress it.

        A view that failed to build and asked for a dock or the centre is
        replaced there by a widget naming it and the reason. When any
        component failed to build or to be set up, a button in the status bar
        counts them and lists them with their tracebacks.
        """
        window = self.main_window
        # the guard outlives the window only if something holds it, and the
        # window holds an event filter weakly
        self._close_guard = CloseGuard(self)
        window.installEventFilter(self._close_guard)
        ColorSchemeButton.pin_to(
            window, ColorSchemeMode.from_config(self._configuration().color_scheme)
        )
        attach(window, self._with_placeholders())
        failures = {**self._failed, **self._not_set_up}
        bar = window.statusBar()
        if failures and bar is not None:
            bar.addPermanentWidget(FailuresButton(failures))
        dresser = self.hooks.get(QtHook.CONFIGURE_MAIN_VIEW)
        if isinstance(dresser, ConfiguresMainView):
            dresser.configure_main_view(window)
        self.restore_layout()

    def _with_placeholders(self) -> dict[str, AttachableComponent]:
        """Return the views in declaration order, a placeholder for each failed one.

        Only a view whose class names a dock or the centre gets one; a menu or
        toolbar item has no place to show it in.
        """
        built = self.views
        views: dict[str, AttachableComponent] = {}
        for name, declaration in self.declarations.items():
            if declaration.kind is not Layer.VIEW:
                continue
            if name in built:
                views[name] = built[name]
                continue
            placement = getattr(declaration.cls, "placement", None)
            if name in self._failed and isinstance(placement, (Dock, Central)):
                views[name] = FailedView(name, self._failed[name], placement)
        return views

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
        the only one that writes.
        """
        if self._main_window is None:
            return
        self.settings.set("window.geometry", encoded(self._main_window.saveGeometry()))
        self.settings.set("window.state", encoded(self._main_window.saveState()))

    def _destroy_widgets(self) -> None:
        """Close and delete the views, then the window that holds them.

        Each widget is closed before it is deleted, so its `closeEvent` runs.

        The views go in reverse build order, as their own teardowns did, and
        the window after the views it docks. Reading it afterwards
        reports an unbuilt session rather than handing back a wrapper whose
        widget is gone. A reference taken before the shutdown is left wrapping
        a destroyed widget, and using it raises `RuntimeError`.

        Emissions still queued for a slot on the main thread are delivered
        first, while the widgets can receive them.
        """
        try:
            emit_queued()
        except Exception:
            logger.exception("Failed to deliver the queued emissions")
        for view in reversed(list(self.views.values())):
            if isinstance(view, QWidget):
                # the only way closeEvent runs: deleting sends none, and
                # closing the window sends none to a view docked inside it
                view.close()
                # C++ may own the widget, so dropping the last Python
                # reference would not end it
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

    # underscored: a hook is declared under its hook point's key, which a
    # public method of that name would collide with
    def _confirm_close(self) -> bool:
        """Return whether the session may close, asking about unsaved changes.

        Closing the window is what calls this, so the title bar, `close()` and
        quitting the application all reach it. A hook installed at
        `QtHook.CONFIRM_CLOSE` answers in place of the prompt.

        Without such a hook, a session that no component asks to be written
        differently from closes without a word, and so does one whose user has
        ticked "don't ask again". Otherwise the prompt offers Save, Discard and
        Cancel.
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
        dialog has accepted it.
        """
        path, _ = QFileDialog.getSaveFileName(
            self._main_window,
            "Save configuration as (comments are not kept)",
            user_documents_dir(),
            "YAML (*.yaml *.yml)",
        )
        if not path:
            return False
        # only the session knows which files it was built from, so the dialog
        # accepts them and write refuses them
        try:
            self.write(path)
        except ConfigurationInUse as reason:
            QMessageBox.warning(self._main_window, "Configuration in use", str(reason))
            return False
        return True

    def _register_actions(self) -> None:
        """Register what the `actions` section declares on the application.

        The disposer is registered with `on_release`, which runs before the
        application is destroyed, so a second session under the same name
        starts against a registry holding nothing of the first.

        Raises
        ------
        ActionError
            If the section is not a list, or an entry is not an action.
        """
        actions = read_actions(self._configuration().actions, type(self).__name__)
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
        build. The `runtime` step has run by now, so the `QApplication` a
        hook is handed exists.
        """
        hook = self.hooks.get(QtHook.DURING_BUILD)
        if isinstance(hook, WrapsBuild):
            return hook.during_build(self.app)
        return nullcontext(self._report)

    def run(self) -> NoReturn:
        """Build, show the window, and hand over to the event loop.

        An exception no slot caught is logged with its traceback, and the
        window carries on.
        """
        # without a hook of its own, the Qt binding ends the process on an
        # exception raised from a slot, and prints nothing
        sys.excepthook = log_unhandled
        self.build()
        # here rather than in build: a session built for a test never shows
        # its window, and that geometry means nothing
        self.on_release(self.save_layout)
        self.app.aboutToQuit.connect(self.shutdown)
        start_emitting_from_queue()
        self.main_window.show()
        sys.exit(self.app.exec())


def log_unhandled(
    kind: type[BaseException], error: BaseException, trace: TracebackType | None
) -> None:
    """Log an exception nothing caught, and let an interrupt end the process."""
    if issubclass(kind, KeyboardInterrupt):
        sys.__excepthook__(kind, error, trace)
        return
    logger.error(
        "Unhandled %s: %s", kind.__name__, error, exc_info=(kind, error, trace)
    )


class CloseGuard(QObject):
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


def encoded(state: QByteArray) -> str:
    """Return *state* as text, the settings file holding JSON rather than bytes."""
    return base64.b64encode(state.data()).decode("ascii")


def application() -> QApplication:
    """Return the running application, or start the one this session needs."""
    return cast("QApplication", QApplication.instance() or QApplication(sys.argv))


AREAS: Final[dict[Area, QtNamespace.DockWidgetArea]] = {
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
        Qt.check_placement(view, placement, f"view {name!r}")
        match placement:
            case Central():
                central[name] = named(name, view, QWidget)
            case Dock():
                add_dock(window, name, named(name, view, QWidget), placement)
            case MenuItem():
                add_menu_item(window, named(name, view, QAction), placement)
            case ToolBarItem():
                add_toolbar_item(window, named(name, view, QAction), placement)
    set_central(window, central)


# taken as 'object' rather than 'AttachableComponent': narrowing a protocol
# against a type variable leaves mypy nothing it can name, and it yields Never
def named(name: str, view: object, required: type[T]) -> T:
    """Return *view* as *required*, named after *name* so it can be found again.

    `Qt.check_placement` has confirmed the type by the time this is called.
    """
    widget = cast("T", view)
    widget.setObjectName(name)
    return widget


def add_dock(window: QMainWindow, name: str, widget: QWidget, placement: Dock) -> None:
    """Put *widget* in a dock of *window*, in the area *placement* names."""
    # Qt matches a dock to its saved place by object name, and drops one that
    # has none, so the component's declared name is what carries the layout
    dock = QDockWidget(name, window)
    dock.setObjectName(name)
    dock.setWidget(widget)
    window.addDockWidget(AREAS[placement.area], dock)


def add_menu_item(window: QMainWindow, action: QAction, placement: MenuItem) -> None:
    """Add *action* to the menu *placement* names, creating that menu if absent.

    Raises
    ------
    TypeError
        If the window has no menu bar.
    """
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


def add_toolbar_item(
    window: QMainWindow, action: QAction, placement: ToolBarItem
) -> None:
    """Add *action* to the toolbar *placement* names, creating it if absent."""
    existing = window.findChildren(QToolBar, placement.toolbar)
    if existing:
        existing[0].addAction(action)
        return
    bar = QToolBar(placement.toolbar, window)
    bar.setObjectName(placement.toolbar)
    window.addToolBar(bar)
    bar.addAction(action)


def set_central(window: QMainWindow, central: dict[str, QWidget]) -> None:
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
