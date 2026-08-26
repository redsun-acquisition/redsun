"""Hook providers used by the container hook tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
