"""Qt-specific application container."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, ClassVar, NoReturn, cast

# psygnal re-exports get/set_async_backend at the top level but not this one
from psygnal._async import clear_async_backend
from psygnal.qt import start_emitting_from_queue
from qtpy.QtWidgets import QApplication

from redsun.aio import set_async_backend
from redsun.containers._hooks import (
    ConfiguresApplication,
    ConfiguresMainView,
    CreatesApplication,
    HookError,
)
from redsun.containers.container import AppContainer
from redsun.containers.qt._mainview import QtMainView

if TYPE_CHECKING:
    from typing import Any

    from redsun.view.qt import QtView

__all__ = ["QtAppContainer"]

logger = logging.getLogger("redsun")


class QtAppContainer(AppContainer):
    """Application container for Qt-based frontends.

    Handles the full Qt lifecycle: ``QApplication`` creation, container
    build, ``QtMainView`` construction, virtual bus connection, and
    ``app.exec()``.

    Parameters
    ----------
    **config : Any
        Configuration options passed to :meth:`AppContainer.__init__`.
    """

    __slots__ = ("_main_view", "_qt_app")

    _hook_protocols: ClassVar[tuple[type, ...]] = (
        *AppContainer._hook_protocols,
        CreatesApplication,
        ConfiguresApplication,
        ConfiguresMainView,
    )

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self._qt_app: QApplication | None = None
        self._main_view: QtMainView | None = None

    @property
    def main_view(self) -> QtMainView:
        """Return the main Qt window.

        Raises
        ------
        RuntimeError
            If the application has not been run yet.
        """
        if self._main_view is None:
            raise RuntimeError("Main view not built. Call run() first.")
        return self._main_view

    def _ensure_application(self) -> QApplication:
        """Return the ``QApplication``, creating one if none is running yet.

        A widget cannot be constructed without one, so every entry point that
        may reach a view goes through here first. A running application is
        adopted as it is; only a session that has none reaches a
        `redsun.qt.QtCreatesApplication` hook.
        """
        if self._qt_app is not None:
            return self._qt_app
        # resolved even when an application is already running, so that a
        # session naming two creators fails the same way under a test suite
        # that owns one and a desktop launch that does not
        creator = self._application_creator()
        running = QApplication.instance()
        if running is not None:
            app = cast("QApplication", running)
        elif creator is None:
            app = QApplication(sys.argv)
        else:
            app = creator.create_application(sys.argv)
        self._qt_app = app
        return app

    def _application_creator(self) -> CreatesApplication[QApplication] | None:
        """Return the hook supplying the application, if any hook claims it.

        Raises
        ------
        HookError
            If more than one hook claims it, naming them: the application a
            session runs on would otherwise be decided by the order of the
            ``hooks`` section.
        """
        claimants: list[CreatesApplication[QApplication]] = [
            hook
            for hook in self._ensure_hooks()
            if isinstance(hook, CreatesApplication)
        ]
        if len(claimants) > 1:
            named = ", ".join(type(hook).__name__ for hook in claimants)
            raise HookError(
                f"create_application is claimed by {len(claimants)} hook providers "
                f"({named}); exactly one may supply the application"
            )
        return claimants[0] if claimants else None

    def _ensure_main_view(self) -> QtMainView:
        """Return the main window, building it from the built views if needed.

        Every `redsun.qt.QtConfiguresMainView` hook runs against it once, as it
        is created, so that a hook sees the window before it is shown.
        """
        if self._main_view is None:
            self._main_view = QtMainView(
                virtual_container=self.virtual_container,
                session_name=self._config.get("session", "Redsun"),
                views=cast("dict[str, QtView]", self.views),
            )
            for hook in self._hooks or ():
                if isinstance(hook, ConfiguresMainView):
                    hook.configure_main_view(self._main_view)
        return self._main_view

    def build(self) -> QtAppContainer:
        """Ensure a ``QApplication`` and an async backend exist, then build.

        If a ``QApplication`` is not yet running (e.g. when ``build()`` is
        called explicitly before ``run()``), one is created here so that
        view components that instantiate ``QWidget`` subclasses have a valid
        application object available.

        Every `redsun.qt.QtConfiguresApplication` hook runs against the
        application before the base build constructs any view, so that a view
        is built against an application already carrying its stylesheet.
        """
        app = self._ensure_application()
        # coroutine slots resolve a backend when they are connected, which
        # happens during the dependency injection phase of super().build()
        set_async_backend()
        for hook in self._ensure_hooks():
            if isinstance(hook, ConfiguresApplication):
                hook.configure_application(app)
        super().build()
        return self

    def shutdown(self) -> None:
        """Shut components down, then tear the async backend down."""
        super().shutdown()
        clear_async_backend()

    def run(self) -> NoReturn:
        """Build and launch the Qt application."""
        qt_app = self._ensure_application()

        if not self.is_built:
            self.build()

        main_view = self._ensure_main_view()

        qt_app.aboutToQuit.connect(self.shutdown)
        start_emitting_from_queue()

        main_view.show()
        sys.exit(qt_app.exec())
