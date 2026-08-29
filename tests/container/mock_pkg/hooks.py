"""Hook providers used by the container hook tests."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from qtpy.QtWidgets import QApplication, QMainWindow

    from redsun.containers import AppContainer

greeted: list[str] = []
"""Every name a `GreetingHook` has greeted with and not yet said goodbye to.

Module level rather than per instance so that a test can assert on what a
container built from a configuration file installed, without holding the
provider the container resolved.
"""

open_spans: list[str] = []
"""Every span a `RecordingSpan` has entered and not left, in entry order."""


class GreetingHook:
    """Serves the neutral point a test container declares, and undoes it."""

    def __init__(self, name: str = "recorded") -> None:
        self.name = name
        self.seen: list[str] = []

    def greet(self, container: AppContainer) -> None:
        self.seen.append(self.name)
        greeted.append(self.name)

    def shutdown(self) -> None:
        greeted.remove(self.name)


class RecordingSpan:
    """Records the steps of the build it wraps, and whether it is still open."""

    def __init__(self, name: str = "recorded") -> None:
        self.name = name
        self.steps: list[str] = []
        self.entries = 0

    @contextmanager
    def during_build(self, app: QApplication) -> Generator[Callable[[str], None]]:
        self.entries += 1
        open_spans.append(self.name)
        try:
            yield self.steps.append
        finally:
            open_spans.remove(self.name)


class FailingShutdownHook:
    """Tears down by raising."""

    def farewell(self, container: AppContainer) -> None:
        pass

    def shutdown(self) -> None:
        raise RuntimeError("teardown blew up")


class NoopHook:
    """Implements no hook protocol at all."""


class BothPointsHook:
    """Serves two points, recording each and its teardown."""

    def __init__(self, name: str = "both") -> None:
        self.name = name
        self.seen: list[str] = []
        self.teardowns = 0

    def greet(self, container: AppContainer) -> None:
        self.seen.append("greet")

    def farewell(self, container: AppContainer) -> None:
        self.seen.append("farewell")

    def shutdown(self) -> None:
        self.teardowns += 1


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
