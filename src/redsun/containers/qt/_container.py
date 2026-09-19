"""Qt-specific application container."""

from __future__ import annotations

import logging
import sys
from contextlib import nullcontext
from typing import TYPE_CHECKING, ClassVar, NoReturn, cast

from psygnal import emit_queued
from psygnal._async import clear_async_backend
from psygnal.qt import start_emitting_from_queue, stop_emitting_from_queue
from qtpy.QtCore import QEvent
from qtpy.QtWidgets import QApplication, QWidget

from redsun.aio import set_async_backend
from redsun.containers.container import AppContainer, _silent

from ..._hooks import (
    ConfiguresApplication,
    ConfiguresMainView,
    CreatesApplication,
    WrapsBuild,
)
from ._mainview import QtMainView

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from contextlib import AbstractContextManager
    from typing import Any

    from redsun.view.qt import QtView

__all__ = ["QtAppContainer"]

logger = logging.getLogger("redsun")


class QtAppContainer(AppContainer):
    """Application container for a Qt frontend.

    Runs the Qt lifecycle: creating the ``QApplication``, building the
    container and the ``QtMainView``, connecting the signal queue, and
    ``app.exec()``.

    Parameters
    ----------
    **config : Any
        Options passed to `AppContainer.__init__`.
    """

    __slots__ = ("_main_view", "_qt_app")

    _hook_keys: ClassVar[Mapping[str, type]] = {
        "create_application": CreatesApplication,
        "configure_application": ConfiguresApplication,
        "during_build": WrapsBuild,
        "configure_main_view": ConfiguresMainView,
    }

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

        No widget can be built without one, so every path reaching a view calls
        this first. A running application is used as is; only when there is
        none is a `redsun.qt.QtCreatesApplication` hook called.
        """
        if self._qt_app is not None:
            return self._qt_app
        # resolved even when an application is already running, so that a
        # malformed hooks section fails the same way under a test suite that
        # owns an application and a desktop launch that does not
        creator = self._ensure_hooks().get("create_application")
        running = QApplication.instance()
        if running is not None:
            app = cast("QApplication", running)
        elif isinstance(creator, CreatesApplication):
            app = cast("QApplication", creator.create_application(sys.argv))
        else:
            app = QApplication(sys.argv)
        self._qt_app = app
        return app

    def _ensure_main_view(self) -> QtMainView:
        """Return the main window, building it from the built views if needed.

        Every `redsun.qt.QtConfiguresMainView` hook runs on it once, when it is
        created and before it is shown.
        """
        if self._main_view is None:
            self._main_view = QtMainView(
                virtual_container=self.virtual_container,
                session_name=self._config["name"],
                views=cast("dict[str, QtView]", self.views),
            )
            hook = self._ensure_hooks().get("configure_main_view")
            if isinstance(hook, ConfiguresMainView):
                hook.configure_main_view(self._main_view)
        return self._main_view

    def build(self) -> QtAppContainer:
        """Ensure a ``QApplication`` and an async backend exist, then build.

        Without a running ``QApplication``, as when ``build()`` is called before
        ``run()``, one is created here so views can construct widgets.

        Every `redsun.qt.QtConfiguresApplication` hook runs on the application
        before any view is built, so views are built with its stylesheet
        already set.
        """
        app = self._ensure_application()
        # coroutine slots resolve a backend when they are connected, which
        # happens during the dependency injection phase of super().build()
        set_async_backend()
        hook = self._ensure_hooks().get("configure_application")
        if isinstance(hook, ConfiguresApplication):
            hook.configure_application(app)
        super().build()
        return self

    def shutdown(self) -> None:
        """Shut components down, then the async backend."""
        super().shutdown()
        clear_async_backend()

    def _destroy(self, components: Sequence[object]) -> None:
        """Destroy the widgets among *components*, and the main window.

        A ``QWidget`` owned by C++ outlives its last Python reference, so only
        ``deleteLater`` ends it. Closing it first gives a widget holding
        resources, such as an embedded canvas, its ``closeEvent``.

        The window goes after the views it docks, and exists only when the
        session started through ``run``: a container built but never run holds
        its views as top-level widgets without a window.

        A reference kept from before shutdown wraps a destroyed widget and
        raises ``RuntimeError`` when used.

        Emissions still queued for a slot with a thread affinity are delivered
        first, while the widgets can receive them.
        """
        self._drain_queued_emissions()
        for component in components:
            if isinstance(component, QWidget):
                component.close()
                component.deleteLater()
        if self._main_view is not None:
            self._main_view.close()
            self._main_view.deleteLater()
            # the property reports an unbuilt window rather than handing back a
            # wrapper whose widget is gone, and a rebuild makes a new one
            self._main_view = None
        if self._qt_app is not None:
            # deleteLater only posts the deletion, and a container shut down
            # without an event loop running would never reach the pass that
            # carries it out
            self._qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def _drain_queued_emissions(self) -> None:
        """Stop emitting from the ``psygnal`` queue and emit what is left in it."""
        stop_emitting_from_queue()
        try:
            emit_queued()
        except Exception as e:  # noqa: BLE001 - a failed delivery must not block teardown
            logger.error(f"Error draining queued emissions: {e}")

    def _during_build(
        self, app: QApplication
    ) -> AbstractContextManager[Callable[[str], None]]:
        """Return the span a `redsun.qt.QtWrapsBuild` hook wraps the build in.

        Without a hook, a context manager yielding a reporter that does nothing,
        so `run` has one path.
        """
        hook = self._ensure_hooks().get("during_build")
        if isinstance(hook, WrapsBuild):
            return hook.during_build(app)
        return nullcontext(_silent)

    def run(self) -> NoReturn:
        """Build and launch the Qt application.

        The build, the window and its first paint happen inside the span a
        `redsun.qt.QtWrapsBuild` hook opens, so a splash screen covers all three
        and closes once the window is up, or when the build fails.
        """
        qt_app = self._ensure_application()

        with self._during_build(qt_app) as report:
            self._report = report
            try:
                if not self.is_built:
                    self.build()

                main_view = self._ensure_main_view()

                qt_app.aboutToQuit.connect(self.shutdown)
                start_emitting_from_queue()

                main_view.show()
                # `show` only schedules the first paint, so without this the
                # span would close over a window that has not drawn yet and a
                # splash screen would uncover an empty desktop
                qt_app.processEvents()
            finally:
                self._report = _silent

        sys.exit(qt_app.exec())
