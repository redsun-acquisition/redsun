"""Hook providers used by the container hook tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qtpy.QtWidgets import QApplication, QMainWindow

    from redsun.containers import AppContainer

installed: list[str] = []
"""Every phase a `RecordingHook` added and has not torn down, in install order.

Module level rather than per instance so that a test can assert on what a
container built from a configuration file installed, without holding the
provider the container resolved.
"""


class RecordingHook:
    """Adds one build phase and removes it again on shutdown."""

    def __init__(self, name: str = "recorded", after: str = "injection") -> None:
        self.name = name
        self.after = after
        self.ran: list[str] = []

    def configure_build(self, container: AppContainer) -> None:
        container.register_phase(self.name, self._run, after=self.after)
        installed.append(self.name)

    def shutdown(self) -> None:
        installed.remove(self.name)

    def _run(self) -> None:
        self.ran.append(self.name)


class NoopHook:
    """Implements no hook protocol at all."""


class FailingShutdownHook:
    """Tears down by raising."""

    def configure_build(self, container: AppContainer) -> None:
        pass

    def shutdown(self) -> None:
        raise RuntimeError("teardown blew up")


class SessionHook:
    """Records the components it can see once the session is built."""

    def __init__(self) -> None:
        self.saw: dict[str, int] | None = None

    def configure_session(self, container: AppContainer) -> None:
        self.saw = {
            "devices": len(container.devices),
            "presenters": len(container.presenters),
            "views": len(container.views),
        }


class PhaseWatcher:
    """Records every phase name the container reports finishing."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def configure_build(self, container: AppContainer) -> None:
        container.sig_phase_complete.connect(self.seen.append)


class QtStyleHook:
    """Styles the application, and records the window it is given."""

    def __init__(self, stylesheet: str = "QWidget { color: red; }") -> None:
        self.stylesheet = stylesheet
        self.window: object | None = None
        self._app: QApplication | None = None

    def configure_application(self, app: QApplication) -> None:
        self._app = app
        app.setStyleSheet(self.stylesheet)

    def configure_main_view(self, view: QMainWindow) -> None:
        self.window = view

    def shutdown(self) -> None:
        if self._app is not None:
            self._app.setStyleSheet("")


class QtOnlyHook:
    """Implements a Qt hook point and nothing a headless container calls."""

    def configure_application(self, app: QApplication) -> None:
        app.setStyleSheet("")


class QtApplicationFactory:
    """Supplies an application the test already owns, and records the call.

    Returns an existing ``QApplication`` rather than building one: a second
    real application cannot be constructed in a process that already has one,
    which every Qt test session does.
    """

    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.calls: list[list[str]] = []

    def create_application(self, argv: list[str]) -> QApplication:
        self.calls.append(argv)
        return self.app
