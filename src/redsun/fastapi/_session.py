"""The FastAPI frontend and the session serving its presenters over HTTP."""

from __future__ import annotations

import logging
import sys
import time
from concurrent.futures import wait
from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING, ClassVar, NoReturn, TypedDict

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from redsun.aio import run_coro

from .._config import RemoteConfig
from ..session._base import Session
from ..session._frontend import Frontend
from ..session._protocols import WebSession
from ._routes import build_api

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from concurrent.futures import Future
    from pathlib import Path

    from .._config import Source
    from ..session._profile import ProfileKind

logger = logging.getLogger("redsun")

START_TIMEOUT = 10.0
"""Seconds `serve` waits for the server to start."""
STOP_TIMEOUT = 10.0
"""Seconds `shutdown` waits for the server to stop."""


class RemoteSettings(TypedDict, total=False):
    """The keys of the `remote` section, for a session class to declare."""

    host: str
    """The address the session listens on."""

    port: int
    """The port the session listens on."""

    origins: list[str]
    """The origins a browser may call the API from."""


class FastAPIFrontend(Frontend):
    """The frontend of a session served by FastAPI, which has no views."""

    foreign_sections = frozenset({"views", "shortcuts", "actions", "color_scheme"})

    @classmethod
    def check_view(cls, view: type, where: str) -> None:
        """Refuse every view.

        Raises
        ------
        TypeError
            Always.
        """
        raise TypeError(f"{where} is a view; a web session has no views")


class FastAPISession(WebSession[FastAPI], Session):
    """A session publishing its presenters as an HTTP and WebSocket API.

    Each presenter with a member marked `remote` gets a route per remote slot
    (`POST /api/{presenter}/{port}`) and per remote property
    (`GET /api/{presenter}/{name}`). Every public signal of those presenters
    is sent on the WebSocket `/api/events`, which the AsyncAPI document at
    `GET /asyncapi.json` describes.

    ```python
    class OnWeb(FastAPISession, Core):
        pass


    OnWeb().serve()
    ```
    """

    __slots__ = ("_app", "_remote")

    frontend = FastAPIFrontend

    remote: ClassVar[RemoteSettings | None] = None
    """The `remote` section of this session: where it serves.

    The session file's `remote` section wins over it, key by key.
    """

    def __init__(
        self,
        config: Source | Sequence[Source] | None = None,
        *,
        log_level: int | str | None = None,
        profile: ProfileKind | None = None,
        profile_dir: str | Path | None = None,
    ) -> None:
        """Prepare an empty session, to be filled by `build`.

        The keywords are those of [`Session`][redsun.Session].
        """
        super().__init__(
            config, log_level=log_level, profile=profile, profile_dir=profile_dir
        )
        self._app: FastAPI | None = None
        self._remote = RemoteConfig()

    @property
    def app(self) -> FastAPI:
        """The FastAPI application serving the session's API.

        Raises
        ------
        RuntimeError
            If read before `build`, which is where it is created.
        """
        if self._app is None:
            raise RuntimeError("Call build() before reading the app")
        return self._app

    def present(self) -> None:
        """Build the API of the presenters with a remote member.

        A presenter breaking a rule of the API is left out of it and counted
        with the build's other problems, but stays built.
        """
        self._remote = self._configuration().remote or RemoteConfig()
        self._app = FastAPI(title=self.name)
        # the app's routes hold the presenters
        self.on_release(partial(setattr, self, "_app", None))
        if self._remote.origins:
            self._app.add_middleware(
                CORSMiddleware,
                allow_origins=self._remote.origins,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        for release in build_api(self._app, self.presenters, self._not_served):
            self.on_release(release)

    def serve(self) -> NoReturn:
        """Build, serve the API where `remote` says, and block until Ctrl+C.

        The address is `127.0.0.1:8000` unless the class or the session file
        sets `remote`. The server's warnings and errors are logged with the
        session's records.

        Ctrl+C stops the server, shuts the session down and exits. The session
        is also shut down when the server fails to start, and when Ctrl+C
        comes before it has.

        Raises
        ------
        RuntimeError
            If the server stops before it starts, such as on a port in use.
        TimeoutError
            If the server neither starts nor stops within `START_TIMEOUT`.
        """
        self.build()
        try:
            server = uvicorn.Server(
                uvicorn.Config(
                    self.app,
                    host=self._remote.host,
                    port=self._remote.port,
                    log_config=None,
                    log_level="warning",
                )
            )
            self.on_release(log_server_to_session())
            running = run_coro(serve_until_stopped(server), return_future=True)
            self.on_release(partial(stop, server, running))
            wait_until_started(server, running)
            until_interrupted()
        finally:
            self.shutdown()
        sys.exit(0)


class ToSession(logging.Handler):
    """Pass each record to the handlers of the `redsun` logger."""

    def emit(self, record: logging.LogRecord) -> None:
        """Hand *record* to the `redsun` logger."""
        logger.handle(record)


def log_server_to_session() -> Callable[[], None]:
    """Send the `uvicorn` logger's records to the session's handlers, and return how to undo it.

    The records stop at the `uvicorn` logger meanwhile, so a handler on the
    root logger receives each of them once, through `redsun`.
    """
    server_logger = logging.getLogger("uvicorn")
    handler = ToSession()
    propagate = server_logger.propagate
    server_logger.addHandler(handler)
    server_logger.propagate = False

    def undo() -> None:
        server_logger.removeHandler(handler)
        server_logger.propagate = propagate

    return undo


async def serve_until_stopped(server: uvicorn.Server) -> None:
    """Run *server*, turning its exit on a failed start into an exception.

    Raises
    ------
    RuntimeError
        If the server could not start.
    """
    try:
        await server.serve()
    # on the shared loop, uvicorn's sys.exit would stop the loop itself
    except SystemExit as e:
        config = server.config
        raise RuntimeError(
            f"the server could not start on {config.host}:{config.port}"
        ) from e


def wait_until_started(server: uvicorn.Server, running: Future[None]) -> None:
    """Block until *server* has started.

    Raises
    ------
    RuntimeError
        If the server stops first.
    TimeoutError
        If it neither starts nor stops within `START_TIMEOUT`.
    """
    deadline = time.monotonic() + START_TIMEOUT
    while not server.started:
        if running.done():
            running.result()
            raise RuntimeError("the server stopped before it started")
        if time.monotonic() > deadline:
            raise TimeoutError(f"the server did not start in {START_TIMEOUT} s")
        time.sleep(0.01)


def stop(server: uvicorn.Server, running: Future[None]) -> None:
    """Ask *server* to exit and wait until it has, at most `STOP_TIMEOUT` seconds.

    A server that failed has stopped already; why is raised where it failed.
    """
    server.should_exit = True
    _, pending = wait([running], STOP_TIMEOUT)
    if pending:
        logger.warning(
            "The server is still running %g s after it was asked to stop", STOP_TIMEOUT
        )


def until_interrupted() -> None:
    """Block the calling thread until Ctrl+C."""
    # a short sleep rather than a wait on an event, which Ctrl+C cannot end on Windows
    with suppress(KeyboardInterrupt):
        while True:
            time.sleep(0.5)
