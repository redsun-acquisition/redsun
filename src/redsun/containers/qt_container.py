"""Qt-specific application container."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, NoReturn

from psygnal.qt import start_emitting_from_queue
from qtpy.QtWidgets import QApplication

from redsun.containers.container import AppContainer
from redsun.view.qt.mainview import QtMainView

if TYPE_CHECKING:
    from typing import Any

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

    def run(self) -> NoReturn:
        """Build and launch the Qt application.

        This method handles the full lifecycle:

        1. Creates the ``QApplication`` instance.
        2. Calls :meth:`build` to instantiate all components.
        3. Constructs :class:`~redsun.view.qt.mainview.QtMainView` and
           docks all built views.
        4. Calls ``connect_to_virtual()`` on all ``VirtualAware`` views.
        5. Starts the ``psygnal`` signal queue bridge.
        6. Shows the main window and enters ``app.exec()``.
        """
        self._qt_app = QApplication(sys.argv)

        if not self.is_built:
            self.build()

        # 3. Construct main view
        session_name = self._config.get("session", "Redsun")
        self._main_view = QtMainView(
            virtual_bus=self.virtual_bus,
            session_name=session_name,
            views=self.views,
        )

        # 4. Connect virtual bus
        self._main_view.connect_to_virtual()

        # 5. Wire shutdown and start psygnal bridge
        self._qt_app.aboutToQuit.connect(self.shutdown)
        start_emitting_from_queue()

        # 6. Show and exec
        self._main_view.show()
        sys.exit(self._qt_app.exec())
