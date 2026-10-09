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
import hashlib
import inspect
import itertools
import json
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
    assert_never,
    cast,
    get_args,
)

from app_model import Action, Application
from app_model.backends.qt import QModelMainWindow, QModelMenu
from app_model.types import MenuRule, ToggleRule
from platformdirs import user_documents_dir
from psygnal import emit_queued
from psygnal.qt import start_emitting_from_queue
from qtpy.QtCore import QByteArray, QEvent, QObject, QRect
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
    QSplitter,
    QTabWidget,
    QToolBar,
    QWidget,
)

from redsun.errors import ConfigurationInUse, HookError
from redsun.view import Column, Placement, Row, Tabs, WindowLayout

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
from ..session._layout import resolved_layout
from ..session._protocols import DesktopSession
from ..view._layout import Split, names_in
from ..view.qt._failed import FailedView, FailuresButton
from ._actions import read_actions
from ._color_scheme import (
    ColorSchemeButton,
    ColorSchemeMode,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from contextlib import AbstractContextManager
    from pathlib import Path
    from types import TracebackType
    from typing import TypeAlias

    from in_n_out import Store

    from .._config import Source
    from .._settings import JsonValue
    from ..ports import SlotThread
    from ..session._declarations import Declaration
    from ..session._profile import ProfileKind
    from ..session._protocols import AttachableComponent, NamedComponent
    from ..view._layout import Node

ASK_ON_CLOSE: Final[str] = "ask_on_close"
"""The settings key holding whether the close prompt still appears."""

SAVE_MENU: Final[str] = "redsun/file"
"""The menu a session's own actions join, which a window may show by name."""

WINDOW_MENU: Final[str] = "redsun/window"
"""The menu holding a toggle for each dock and "Reset layout", shown by the session's window.

The session adds it at the end of the menu bar unless the bar already shows it.
"""

__all__ = [
    "WINDOW_MENU",
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

AREAS: Final[dict[Area, QtNamespace.DockWidgetArea]] = {
    "left": QtNamespace.DockWidgetArea.LeftDockWidgetArea,
    "right": QtNamespace.DockWidgetArea.RightDockWidgetArea,
    "top": QtNamespace.DockWidgetArea.TopDockWidgetArea,
    "bottom": QtNamespace.DockWidgetArea.BottomDockWidgetArea,
}
"""The Qt dock area of each edge a `Dock` can name."""

EDGE_NAMES: Final = frozenset(get_args(Area))
"""The words for an edge of the window."""

DIRECT_CHILDREN: Final = QtNamespace.FindChildOption.FindDirectChildrenOnly
"""Find a widget's own children, not theirs."""

HORIZONTAL: Final = QtNamespace.Orientation.Horizontal
"""Side by side."""

VERTICAL: Final = QtNamespace.Orientation.Vertical
"""Stacked."""


@dataclass(frozen=True)
class Dock(Placement):
    """A panel against one edge of the window, tabbed with the docks of its group.

    Raises
    ------
    ValueError
        If `area` names no edge of the window.
    """

    area: Area
    """Edge the panel sits against."""

    group: str | None = None
    """Name of the docks it is tabbed with on the same edge; `None` for none."""

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
    regions: ClassVar[Mapping[str, type[Row | Column | Tabs]]] = {
        "center": Tabs,
        "left": Column,
        "right": Column,
        "top": Row,
        "bottom": Row,
    }
    hides: ClassVar[bool] = True

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
    def read_placement(cls, value: object) -> Placement:
        """Return the Qt placement a session file's *value* names.

        `left`, `right`, `top` or `bottom` is a dock against that edge and
        `central` the main area; `{dock: <edge>, group: <name>}` a dock tabbed
        with its group, `{menu: <name>}` an entry in that menu and
        `{toolbar: <name>}` an entry in that toolbar.

        Raises
        ------
        ValueError
            If *value* is none of these.
        """
        match value:
            case "central":
                return Central()
            case str(edge) if edge in EDGE_NAMES:
                return Dock(cast("Area", edge))
            case {"dock": str(edge), "group": str(group), **rest} if (
                not rest and edge in EDGE_NAMES
            ):
                return Dock(cast("Area", edge), group=group)
            case {"dock": str(edge), **rest} if not rest and edge in EDGE_NAMES:
                return Dock(cast("Area", edge))
            case {"menu": str(menu), **rest} if not rest:
                return MenuItem(menu)
            case {"toolbar": str(toolbar), **rest} if not rest:
                return ToolBarItem(toolbar)
        raise ValueError(
            f"placement {value!r} names nothing Qt attaches; give one of "
            "left, right, top, bottom, central, {dock: <edge>, group: <name>}, "
            "{menu: <name>} or {toolbar: <name>}"
        )

    @classmethod
    def region_of(cls, placement: Placement) -> tuple[str, str | None] | None:
        """Return `center` for `Central`, a dock's edge and group, and `None` for a menu or toolbar item."""
        match placement:
            case Central():
                return "center", None
            case Dock(area=area, group=group):
                return area, group
        return None

    @classmethod
    def layout_problems(cls, layout: WindowLayout) -> list[str]:
        """Return what Qt cannot show of *layout*, a share for the centre and opposite edges filling the window included."""
        problems = super().layout_problems(layout)
        for first, second in (("left", "right"), ("top", "bottom")):
            together = layout.sizes.get(first, 0) + layout.sizes.get(second, 0)
            if together >= 1:
                problems.append(
                    f"layout.sizes: {first} and {second} take {together:g} of the "
                    "window together and leave nothing for the centre"
                )
        if "center" in layout.sizes:
            problems.append(
                "layout.sizes.center: the centre takes what the docks leave; "
                "give shares to the edges"
            )
        return problems

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
        "_default_state",
        "_main_window",
        "_model",
        "_qt_app",
        "_shown_layout",
        "_sized",
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
        profile: ProfileKind | None = None,
        profile_dir: str | Path | None = None,
    ) -> None:
        """Prepare an empty container, to be filled by `build`.

        The keywords are those of [`Session`][redsun.Session].
        """
        super().__init__(
            config, log_level=log_level, profile=profile, profile_dir=profile_dir
        )
        self._close_guard: CloseGuard | None = None
        self._default_state: QByteArray | None = None
        self._shown_layout = WindowLayout()
        self._sized = False
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

        Raises
        ------
        HookError
            If a `create_application` hook returns anything but a
            `QApplication`.
        """
        super().start_runtime()
        hooks = self.hooks
        creator = hooks.get(QtHook.CREATE_APPLICATION)
        if QApplication.instance() is None and isinstance(creator, CreatesApplication):
            qt_app = creator.create_application(sys.argv)
            if not isinstance(qt_app, QApplication):
                raise HookError(
                    f"hook provider {type(creator).__name__!r} at "
                    f"{QtHook.CREATE_APPLICATION.value!r} returned "
                    f"{type(qt_app).__name__}, not a QApplication"
                )
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
        return set(self.main_window.findChildren(QWidget, options=DIRECT_CHILDREN))

    def present(self) -> None:
        """Put every view where it asks to be in the window, and ready the window to show.

        A view that failed to build and asked for a dock or the centre is
        replaced there by a widget naming it and the reason. When any
        component failed to build or to be set up, a button in the status bar
        counts them and lists them with their tracebacks. A Window menu,
        added after the main-view hook has run, shows or hides each dock and
        puts every dock back where its placement says.
        """
        window = self.main_window
        # the guard outlives the window only if something holds it, and the
        # window holds an event filter weakly
        self._close_guard = CloseGuard(self)
        window.installEventFilter(self._close_guard)
        ColorSchemeButton.pin_to(
            window, ColorSchemeMode.from_config(self._configuration().color_scheme)
        )
        views = self._with_placeholders()
        self._shown_layout = self.resolve_layout()
        attach(window, views, self._declared_placements(), self._shown_layout)
        earlier = set(window.findChildren(QDockWidget, options=DIRECT_CHILDREN))
        failures = {**self._failed, **self._not_set_up}
        bar = window.statusBar()
        if failures and bar is not None:
            bar.addPermanentWidget(FailuresButton(failures))
        dresser = self.hooks.get(QtHook.CONFIGURE_MAIN_VIEW)
        if isinstance(dresser, ConfiguresMainView):
            dresser.configure_main_view(window)
        self._register_window_actions(views, earlier)
        self._default_state = window.saveState()
        self.restore_layout()

    def _with_placeholders(self) -> dict[str, AttachableComponent]:
        """Return the views in declaration order, a placeholder for each failed one.

        Only a view whose declaration names a dock or the centre gets one; a menu or
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
            placement = declaration.placement
            if name in self._failed and isinstance(placement, (Dock, Central)):
                views[name] = FailedView(name, self._failed[name], placement)
        return views

    def _declared_placements(self) -> dict[str, Placement]:
        """Return, by name, the placement each view's declaration chose."""
        return {
            name: declaration.placement
            for name, declaration in self.declarations.items()
            if declaration.kind is Layer.VIEW and declaration.placement is not None
        }

    def restore_layout(self) -> None:
        """Put the window back where this user last left it.

        Runs once every dock exists, since Qt places a dock by object name and
        ignores one it has not seen. The geometry always comes back. The docks
        come back only while the views ask for the places they asked for when
        the layout was saved, so a changed placement shows on the next run; a
        layout saved without that record is restored. The centre's splitters
        and current tabs come back with the docks.
        """
        self._sized = False
        try:
            self._sized = self._restore_saved_layout()
        except ValueError:
            logger.warning(
                "The window layout saved in %s could not be read, so the docks "
                "start where their placements say",
                self.settings.path,
            )

    def _restore_saved_layout(self) -> bool:
        """Restore the saved geometry, and the docks and centre while the layout matches, and return whether they came back.

        Raises
        ------
        ValueError
            If a saved value is not the base64 text the session writes.
        """
        geometry = self.settings.get("window.geometry")
        if isinstance(geometry, str):
            self.main_window.restoreGeometry(QByteArray(base64.b64decode(geometry)))
        state = self.settings.get("window.state")
        if not isinstance(state, str):
            return False
        saved = self.settings.get("window.layout")
        if saved is not None and saved != self._layout_fingerprint():
            logger.info(
                "The views of %r are placed differently from when %s was saved, "
                "so the docks start where their placements say",
                self.name,
                self.settings.path,
            )
            return False
        self.main_window.restoreState(
            QByteArray(base64.b64decode(state, validate=True))
        )
        restore_centre(
            self.main_window, self._shown_layout, self.settings.get("window.center")
        )
        return True

    def _layout_fingerprint(self) -> str:
        """Return a digest of the layout the window starts with, which a saved layout is kept for.

        The digest covers the layout the session declares, the name of every
        view, and the layout those resolve to. Each view counts with the
        placement its declaration holds, so one that fails to build does not
        discard the saved layout. A view whose class answers `placement` from a
        property has none there, so changing what the property answers keeps
        the saved layout, while moving the view in the declared layout does
        not.
        """
        placements: dict[str, Placement | None] = {
            name: declaration.placement
            for name, declaration in self.declarations.items()
            if declaration.kind is Layer.VIEW
        }
        layout, _ = resolved_layout(self._window_layout, placements, self.frontend)
        declared = self._window_layout or WindowLayout()
        content = [layout.fingerprint(), declared.fingerprint(), list(placements)]
        return hashlib.sha256(json.dumps(content).encode()).hexdigest()

    def save_layout(self) -> None:
        """Remember where this user left the window, and the placements it was left with.

        `run` asks for this as the session ends, so a window that was shown is
        the only one that writes.
        """
        if self._main_window is None:
            return
        self.settings.set("window.geometry", encoded(self._main_window.saveGeometry()))
        self.settings.set("window.state", encoded(self._main_window.saveState()))
        self.settings.set("window.layout", self._layout_fingerprint())
        self.settings.set(
            "window.center", centre_state(self._main_window, self._shown_layout)
        )

    def _register_window_actions(
        self, views: Mapping[str, AttachableComponent], earlier: set[QDockWidget]
    ) -> None:
        """Register a toggle for each dock and "Reset layout", and show them as the Window menu.

        The docks are those of *views*, and those added since *earlier* was
        taken that have an object name no other dock has. A dock a view adds
        by itself gets no toggle, and a session with no dock shows no such
        menu. A menu bar that already shows `WINDOW_MENU` gets no second one.
        The views placed in a menu named Window move into this one, above the
        toggles.
        """
        window = self.main_window
        docks = {
            name: dock
            for name in views
            if (dock := window.findChild(QDockWidget, name, DIRECT_CHILDREN))
            is not None
        }
        for dock in window.findChildren(QDockWidget, options=DIRECT_CHILDREN):
            name = dock.objectName()
            if dock not in earlier and name and name not in docks:
                docks[name] = dock
        if not docks:
            return
        actions = [dock_toggle(self.name, dock) for dock in docks.values()]
        actions.append(
            Action(
                id=f"{self.name}.reset_layout",
                title="Reset layout",
                callback=self._reset_layout,
                menus=[MenuRule(id=WINDOW_MENU, group="2_layout")],
            )
        )
        self.on_release(self.model.register_actions(actions))
        bar = window.menuBar()
        if bar is None or window.findChild(QModelMenu, WINDOW_MENU) is not None:
            return
        menu = QModelMenu(WINDOW_MENU, self.model, "Window", window)
        bar.addMenu(menu)
        # findChildren, since pyqt6 types findChild as never returning None
        placed = window.findChildren(QMenu, "Window", options=DIRECT_CHILDREN)
        if not placed:
            return
        bar.removeAction(placed[0].menuAction())
        items = placed[0].actions()

        # connected after the menu's own handler, which empties the menu
        # before refilling it from the registry
        def keep_items(changed: set[str]) -> None:
            if WINDOW_MENU in changed:
                first = menu.actions()[0]
                menu.insertActions(first, items)
                menu.insertSeparator(first)

        keep_items({WINDOW_MENU})
        self.model.menus.menus_changed.connect(keep_items)
        self.on_release(lambda: self.model.menus.menus_changed.disconnect(keep_items))

    def _reset_layout(self) -> None:
        """Put every dock back where it was before a saved layout was restored, at its declared size."""
        if self._default_state is not None:
            self.main_window.restoreState(self._default_state)
        fit_layout(self.main_window, self._shown_layout)

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

    def show(self) -> None:
        """Show the window, giving its regions the sizes the layout declares unless a saved layout was restored.

        The sizes are given once, so showing the window again keeps what the
        user changed. `run` calls it; a script that runs the event loop itself
        calls it in place of showing `main_window`.
        """
        self.main_window.show()
        if not self._sized:
            fit_layout(self.main_window, self._shown_layout)
            self._sized = True

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
        self.show()
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
        if obj is None or event is None or event.type() != QEvent.Type.Close:
            return False
        session = self._session()
        if session is not None and not session._confirm_close():
            event.ignore()
            return True
        return super().eventFilter(obj, event)


def encoded(state: QByteArray) -> str:
    """Return *state* as text, the settings file holding JSON rather than bytes."""
    return base64.b64encode(state.data()).decode("ascii")


def dock_toggle(session: str, dock: QDockWidget) -> Action[[], None]:
    """Return the action showing *dock* while it is hidden and hiding it while it is shown.

    It is checked while the dock is shown, which a menu reads as it opens.
    """

    def toggle() -> None:
        dock.setVisible(dock.isHidden())

    def shown() -> bool:
        return not dock.isHidden()

    return Action(
        id=f"{session}.toggle_dock.{dock.objectName()}",
        title=dock.windowTitle(),
        callback=toggle,
        toggled=ToggleRule(get_current=shown),
        menus=[MenuRule(id=WINDOW_MENU, group="1_docks")],
    )


def application() -> QApplication:
    """Return the running application, or start the one this session needs."""
    return cast("QApplication", QApplication.instance() or QApplication(sys.argv))


def attach(
    window: QMainWindow,
    views: Mapping[str, AttachableComponent],
    placements: Mapping[str, Placement] | None = None,
    layout: WindowLayout | None = None,
) -> None:
    """Attach every view of *views* to *window*, where *layout* puts it or else where it asks.

    *placements* gives, by name, the placement a view's declaration chose;
    any other view is placed where its `placement` asks. *layout* is a
    resolved layout, such as
    [`Session.resolve_layout`][redsun.Session.resolve_layout] returns;
    without one the placements alone decide, docks of one edge and group
    tabbed together in the order of *views*. Menu and toolbar items go where
    their placement asks.

    Raises
    ------
    TypeError
        If a view asks for a placement Qt does not attach, or is not the
        toolkit type that placement demands.
    ValueError
        If *layout* leaves out a view that asks for a dock or the centre, or
        names one that is not in *views*.
    """
    asked = {
        name: (placements or {}).get(name) or view.placement
        for name, view in views.items()
    }
    for name, view in views.items():
        Qt.check_placement(view, asked[name], f"view {name!r}")
    if layout is None:
        layout, _ = resolved_layout(None, dict(asked), Qt)
    placed = set(layout.names)
    unknown = [name for name in layout.names if name not in views]
    if unknown:
        raise ValueError(
            f"the window layout names {', '.join(map(repr, unknown))}, which "
            "are not among the views to attach"
        )
    missing = [
        name
        for name, placement in asked.items()
        if Qt.region_of(placement) is not None and name not in placed
    ]
    if missing:
        raise ValueError(
            f"the window layout leaves out {', '.join(map(repr, missing))}, "
            "which ask for a dock or the centre"
        )
    widgets = {
        name: named(name, view, QWidget)
        for name, view in views.items()
        if name in placed
    }
    docks: dict[str, QDockWidget] = {}
    for region, node in layout.regions.items():
        if region == "center":
            window.setCentralWidget(central_widget(node, widgets))
            continue
        made = {name: make_dock(window, name, widgets[name]) for name in names_in(node)}
        add_docks(window, region, node, made)
        docks.update(made)
    for name in layout.hidden:
        if name in docks:
            docks[name].hide()
        else:
            logger.warning(
                "View %r sits in the centre, which starts nothing hidden", name
            )
    for name, view in views.items():
        match asked[name]:
            case MenuItem() as item:
                add_menu_item(window, named(name, view, QAction), item)
            case ToolBarItem() as item:
                add_toolbar_item(window, named(name, view, QAction), item)


# taken as 'object' rather than 'AttachableComponent': narrowing a protocol
# against a type variable leaves mypy nothing it can name, and it yields Never
def named(name: str, view: object, required: type[T]) -> T:
    """Return *view* as *required*, named after *name* so it can be found again.

    `Qt.check_placement` has confirmed the type by the time this is called.
    """
    widget = cast("T", view)
    widget.setObjectName(name)
    return widget


def make_dock(window: QMainWindow, name: str, widget: QWidget) -> QDockWidget:
    """Return a dock of *window* holding *widget*, named after the view."""
    # Qt matches a dock to its saved place by object name, and drops one that
    # has none, so the component's declared name is what carries the layout
    dock = QDockWidget(name, window)
    dock.setObjectName(name)
    dock.setWidget(widget)
    return dock


def add_docks(
    window: QMainWindow, region: str, node: Node, docks: Mapping[str, QDockWidget]
) -> None:
    """Put *docks* against the edge *region* names, arranged as *node*."""
    area = AREAS[cast("Area", region)]
    first = docks[next(names_in(node))]
    window.addDockWidget(area, first)
    spread(window, area, Qt.regions[region], node, first, docks)


def spread(
    window: QMainWindow,
    area: QtNamespace.DockWidgetArea,
    natural: type,
    node: Node,
    anchor: QDockWidget,
    docks: Mapping[str, QDockWidget],
) -> None:
    """Arrange the docks of *node* around *anchor*, the dock of its first view, already in place.

    The first view of every child is placed before any child is arranged, so
    a child splits only its own share. *natural* is how the edge lines docks
    up by itself; a split across it needs dock nesting.
    """
    match node:
        case str():
            return
        case Tabs(names=names, current=current):
            for name in names[1:]:
                window.addDockWidget(area, docks[name])
                window.tabifyDockWidget(anchor, docks[name])
            docks[current or names[0]].raise_()
        case Split(children=children):
            if type(node) is not natural:
                window.setDockNestingEnabled(True)
            orientation = HORIZONTAL if isinstance(node, Row) else VERTICAL
            firsts = [docks[next(names_in(child))] for child in children]
            for before, after in itertools.pairwise(firsts):
                window.splitDockWidget(before, after, orientation)
            for child, first in zip(children, firsts, strict=True):
                spread(window, area, natural, child, first, docks)
        case _:
            assert_never(node)


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


def central_widget(node: Node, widgets: Mapping[str, QWidget]) -> QWidget:
    """Return what shows *node* in the centre: a view, tabs, or a splitter."""
    match node:
        case str():
            return widgets[node]
        case Tabs(names=names, current=current):
            tabs = QTabWidget()
            for name in names:
                tabs.addTab(widgets[name], name)
            tabs.setCurrentIndex(names.index(current) if current else 0)
            return tabs
        case Split(children=children):
            splitter = QSplitter(HORIZONTAL if isinstance(node, Row) else VERTICAL)
            for child in children:
                splitter.addWidget(central_widget(child, widgets))
            return splitter
        case _:
            assert_never(node)


def shares(count: int, sizes: Sequence[float] | None) -> list[float]:
    """Return the share of its space each of *count* children takes, by *sizes* or equally."""
    weights = list(sizes) if sizes is not None else [1.0] * count
    total = sum(weights)
    return [weight / total for weight in weights]


def declares_sizes(node: Node) -> bool:
    """Return whether a split in *node* gives its children weights."""
    if isinstance(node, Split):
        return node.sizes is not None or any(
            declares_sizes(child) for child in node.children
        )
    return False


def extents(node: Node, width: int, height: int) -> Iterator[tuple[str, int, int]]:
    """Yield each view of *node* with the width and height its share of *width* by *height* gives it."""
    match node:
        case str():
            yield node, width, height
        case Tabs(names=names):
            for name in names:
                yield name, width, height
        case Split(children=children, sizes=sizes):
            across = isinstance(node, Row)
            for child, share in zip(
                children, shares(len(children), sizes), strict=True
            ):
                if across:
                    yield from extents(child, round(width * share), height)
                else:
                    yield from extents(child, width, round(height * share))
        case _:
            assert_never(node)


def fit_docks(
    window: QMainWindow, region: str, node: Node, share: float | None
) -> None:
    """Give the docks of *region* their share of *window*, and each split of *node* its weights."""
    docks = {
        dock.objectName(): dock
        for dock in window.findChildren(QDockWidget, options=DIRECT_CHILDREN)
        if not dock.isHidden()
    }
    box = QRect()
    for name in names_in(node):
        # a tab behind another reports no useful geometry
        if name in docks and docks[name].geometry().intersects(window.rect()):
            box = box.united(docks[name].geometry())
    width, height = box.width(), box.height()
    if share is not None:
        if region in ("left", "right"):
            width = round(window.width() * share)
        else:
            height = round(window.height() * share)
    sized = [
        (docks[name], w, h)
        for name, w, h in extents(node, width, height)
        if name in docks
    ]
    window.resizeDocks(
        [dock for dock, _, _ in sized], [w for _, w, _ in sized], HORIZONTAL
    )
    window.resizeDocks(
        [dock for dock, _, _ in sized], [h for _, _, h in sized], VERTICAL
    )


def fit_centre(node: Node, widget: QWidget | None) -> None:
    """Give each splitter of the centre its weights, and each tab group its current tab."""
    if isinstance(node, Tabs) and isinstance(widget, QTabWidget):
        widget.setCurrentIndex(node.names.index(node.current) if node.current else 0)
    elif isinstance(node, Split) and isinstance(widget, QSplitter):
        total = sum(widget.sizes())
        widget.setSizes(
            [round(total * share) for share in shares(len(node.children), node.sizes)]
        )
        for index, child in enumerate(node.children):
            fit_centre(child, widget.widget(index))


def fit_layout(window: QMainWindow, layout: WindowLayout) -> None:
    """Give each region and split of *layout* its share of *window* as shown, and the centre its current tabs.

    An edge with no share and no weights keeps the sizes Qt gave it.
    """
    for region, node in layout.regions.items():
        if region == "center":
            fit_centre(node, window.centralWidget())
        elif region in layout.sizes or declares_sizes(node):
            fit_docks(window, region, node, layout.sizes.get(region))


def centre_parts(node: Node, widget: QWidget | None) -> list[QSplitter | QTabWidget]:
    """Return the splitters and tab groups the centre was built with for *node*, in order."""
    if isinstance(node, Tabs) and isinstance(widget, QTabWidget):
        return [widget]
    if isinstance(node, Split) and isinstance(widget, QSplitter):
        parts: list[QSplitter | QTabWidget] = [widget]
        for index, child in enumerate(node.children):
            parts.extend(centre_parts(child, widget.widget(index)))
        return parts
    return []


def centre_state(window: QMainWindow, layout: WindowLayout) -> list[JsonValue]:
    """Return where the user left the centre's splitters, and which tabs are current."""
    node = layout.regions.get("center")
    if node is None:
        return []
    return [
        encoded(part.saveState())
        if isinstance(part, QSplitter)
        else part.currentIndex()
        for part in centre_parts(node, window.centralWidget())
    ]


def restore_centre(window: QMainWindow, layout: WindowLayout, state: object) -> None:
    """Put the centre's splitters and tabs back as *state*, from `centre_state`, recorded them.

    A state of another shape is ignored.
    """
    node = layout.regions.get("center")
    parts = [] if node is None else centre_parts(node, window.centralWidget())
    if not isinstance(state, list) or len(state) != len(parts):
        return
    for part, value in zip(parts, state, strict=True):
        if isinstance(part, QSplitter) and isinstance(value, str):
            part.restoreState(QByteArray(base64.b64decode(value)))
        elif isinstance(part, QTabWidget) and isinstance(value, int):
            part.setCurrentIndex(value)
