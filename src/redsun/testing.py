"""Pytest fixtures for testing components, sessions and services.

A suite loads them with `-p redsun.testing`, in `addopts` or on the command
line. Loading them makes every test keep session settings, session logs,
acquisition data and catalogs under its `tmp_path`, drop the `psygnal`
emissions it left queued, and collect a Qt test's garbage on the main thread.
On Windows under Qt's `offscreen` platform, they also point Qt at the system
fonts, which that platform otherwise lacks.
The module defines no `qapp`, so it combines with `pytest-qt`.
"""

from __future__ import annotations

import gc
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeVar

import pytest
from psygnal._queue import QueuedCallback

from redsun.aio import run_coro
from redsun.log import SERVICE_LOGGER, SessionFileHandler, logger
from redsun.services import Service
from redsun.session import Session

from .services._transports import CHANNEL_ACCESS, TRANSPORTS

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

    from redsun.session import Launch

    from ._config import Source

__all__ = [
    "BuildSession",
    "StartService",
    "build",
    "collect_qt_garbage",
    "config_home",
    "data_directory",
    "empty_emission_queue",
    "log_directory",
    "start_service",
]

ADDRESS_LISTS = ("EPICS_CA_ADDR_LIST", "EPICS_PVA_ADDR_LIST")
"""The environment variables a started service adds its address to."""

SessionT = TypeVar("SessionT", bound=Session)


class BuildSession(Protocol):
    """Build a session, and hand it back typed as what was asked for."""

    def __call__(
        self,
        container: type[SessionT] | SessionT,
        config: Source | Sequence[Source] | None = ...,
        /,
    ) -> SessionT:
        """Build *container*, a session class made with *config*, or a session."""
        ...


class StartService(Protocol):
    """Start a service as a session declaring it would, and hand it back."""

    def __call__(
        self, name: str, launch: Launch, /, *, transport: str = ...
    ) -> Service:
        """Start the service *launch* describes, declared under *name*.

        *transport* is the one a session file names under
        `services.transport`: `channel-access` or `pv-access`.
        """
        ...


@pytest.fixture
def build() -> Generator[BuildSession, None, None]:
    """Return a function building a session, shut down when the test ends.

    It takes a session class, made with the configuration given and laid over
    what the class declares, or a session already made. Sessions are shut
    down in reverse order; one the test shut down itself runs nothing again.
    A shutdown that raises does not stop the others: once every session has
    been shut down, the fixture raises that error, or an `ExceptionGroup` of
    all of them when more than one session raised.
    """
    built: list[Session] = []

    def build_one(
        container: type[SessionT] | SessionT,
        config: Source | Sequence[Source] | None = None,
        /,
    ) -> SessionT:
        unbuilt = container(config) if isinstance(container, type) else container
        session = unbuilt.build()
        built.append(session)
        return session

    yield build_one
    errors: list[Exception] = []
    for session in reversed(built):
        try:
            session.shutdown()
        except Exception as e:  # noqa: BLE001 - raised once every session is shut down
            errors.append(e)
    if len(errors) == 1:
        raise errors[0]
    if errors:
        raise ExceptionGroup("sessions could not shut down", errors)


@pytest.fixture(autouse=True)
def log_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Path, None, None]:
    """Write session log files under `tmp_path`, closing any the test left open."""
    monkeypatch.setattr("redsun.log.user_data_dir", lambda *a, **k: str(tmp_path))
    yield tmp_path / "logs"
    loggers = [
        logging.getLogger(name)
        for name in list(logging.Logger.manager.loggerDict)
        if name.startswith(SERVICE_LOGGER)
    ]
    for owner in (logger, *loggers):
        for handler in [h for h in owner.handlers if isinstance(h, SessionFileHandler)]:
            owner.removeHandler(handler)
            handler.close()


@pytest.fixture(autouse=True)
def data_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put the default root of acquisition files and catalogs under `tmp_path`."""
    root = tmp_path / "data"
    monkeypatch.setattr("redsun.path_provider.user_data_dir", lambda *a, **k: str(root))
    return root


@pytest.fixture(autouse=True)
def config_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Keep saved session settings in a `config` folder under `tmp_path`."""
    root = tmp_path / "config"
    monkeypatch.setattr("redsun._settings.user_config_dir", lambda *a, **k: str(root))
    return root


def pytest_configure(config: pytest.Config) -> None:
    """Give Qt's `offscreen` platform the system fonts on Windows.

    There it finds no fonts of its own, so once an icon font is loaded every
    text falls back to it and measures nothing.
    """
    offscreen = os.environ.get("QT_QPA_PLATFORM", "").startswith("offscreen")
    if offscreen and sys.platform == "win32":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        os.environ.setdefault("QT_QPA_FONTDIR", str(fonts))


@pytest.fixture(autouse=True)
def collect_qt_garbage(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Collect after each test using `qapp`, on the main thread.

    A widget the test left in a reference cycle would otherwise be freed by
    the next collection, which a later test may run on another thread;
    `pyside6` aborts when a widget is destroyed off the GUI thread.
    """
    yield
    if "qapp" in request.fixturenames:
        gc.collect()


@pytest.fixture(autouse=True)
def empty_emission_queue() -> Generator[None, None, None]:
    """Drop every psygnal emission the test left queued for another thread.

    Left queued, an emission is delivered by the next test running the event
    loop, to whatever its target has become; a destroyed widget ends the
    interpreter.
    """
    yield
    # psygnal offers no public way to drop queued emissions
    for queue in QueuedCallback._GLOBAL_QUEUE.values():
        while not queue.empty():
            queue.get_nowait()


@pytest.fixture
def start_service(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[StartService, None, None]:
    """Return a function starting a declared service, stopped when the test ends.

    Once the services have stopped, their transports are released and the
    EPICS address lists they added themselves to are restored, as when a
    session ends.
    """
    for variable in ADDRESS_LISTS:
        monkeypatch.setenv(variable, os.environ.get(variable, ""))
    started: list[Service] = []

    def start(
        name: str, launch: Launch, /, *, transport: str = CHANNEL_ACCESS
    ) -> Service:
        given = {key: value for key, value in vars(launch).items() if value is not None}
        service = Service(name, transport=transport, **given)
        service.start()
        started.append(service)
        return service

    yield start
    for service in reversed(started):
        service.stop()
    for transport in {service.transport for service in started}:
        run_coro(TRANSPORTS[transport].release())
