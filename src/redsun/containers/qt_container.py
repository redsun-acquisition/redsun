"""Qt-specific application container."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, NoReturn, cast

from psygnal.qt import start_emitting_from_queue
from qtpy.QtWidgets import QApplication

from redsun.containers.container import AppContainer
from redsun.view.qt.mainview import QtMainView

if TYPE_CHECKING:
    from typing import Any

    from sunflare.view.qt import QtView

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

    __slots__ = ("_qt_app", "_main_view")

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

    def build(self) -> QtAppContainer:
        """Ensure a ``QApplication`` exists, then build all components.

        If a ``QApplication`` is not yet running (e.g. when ``build()`` is
        called explicitly before ``run()``), one is created here so that
        view components that instantiate ``QWidget`` subclasses have a valid
        application object available.
        """
        if self._qt_app is None:
            self._qt_app = cast(
                "QApplication", QApplication.instance() or QApplication(sys.argv)
            )
        super().build()
        return self

    def run(self) -> NoReturn:
        """Build and launch the Qt application."""
        if self._qt_app is None:
            self._qt_app = cast(
                "QApplication", QApplication.instance() or QApplication(sys.argv)
            )

        if not self.is_built:
            self.build()

        assert self._qt_app is not None  # guaranteed by build() above
        session_name = self._config.get("session", "Redsun")
        self._main_view = QtMainView(
            virtual_bus=self.virtual_bus,
            session_name=session_name,
            views=cast("dict[str, QtView]", self.views),
        )

        # 4. Connect virtual bus
        self._main_view.connect_to_virtual()

        # 5. Wire shutdown and start psygnal bridge
        self._qt_app.aboutToQuit.connect(self.shutdown)
        start_emitting_from_queue()

        # 6. Show and exec
        self._main_view.show()
        sys.exit(self._qt_app.exec())
