"""The FastAPI frontend and the session serving its presenters over HTTP."""

from __future__ import annotations

import sys
import time
from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING, NoReturn

import uvicorn
from fastapi import FastAPI

from redsun.aio import run_coro

from ..session._base import Session
from ..session._frontend import Frontend
from ..session._protocols import WebSession
from ._routes import build_api

if TYPE_CHECKING:
    from collections.abc import Sequence
    from concurrent.futures import Future
    from pathlib import Path

    from .._config import Source
    from ..session._profile import ProfileKind

HOST = "127.0.0.1"
PORT = 8000
STOP_TIMEOUT = 10.0
"""Seconds `shutdown` waits for the server to stop."""


class FastAPIFrontend(Frontend):
    """The frontend of a session served by FastAPI, which has no views."""

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
    is sent on the WebSocket `/api/events`, and `GET /api/signals` describes
    the arguments of each.

    ```python
    class OnWeb(FastAPISession, Core):
        pass


    OnWeb().serve()
    ```
    """

    __slots__ = ("_app",)

    frontend = FastAPIFrontend

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
        self._app = FastAPI(title=self.name)
        for release in build_api(self._app, self.presenters, self._not_set_up):
            self.on_release(release)

    def serve(self) -> NoReturn:
        """Build, serve the API on `127.0.0.1:8000`, and block until Ctrl+C.

        Ctrl+C stops the server, shuts the session down and exits.

        Raises
        ------
        RuntimeError
            If the server stops before it starts, such as on a port in use.
        """
        self.build()
        server = uvicorn.Server(
            uvicorn.Config(self.app, host=HOST, port=PORT, log_level="warning")
        )
        running = run_coro(serve_until_stopped(server), return_future=True)
        self.on_release(partial(stop, server, running))
        while not server.started:
            if running.done():
                running.result()
                raise RuntimeError("the server stopped before it started")
            time.sleep(0.01)
        until_interrupted()
        self.shutdown()
        sys.exit(0)


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
        raise RuntimeError(f"the server could not start on {HOST}:{PORT}") from e


def stop(server: uvicorn.Server, running: Future[None]) -> None:
    """Ask *server* to exit and wait until it has."""
    server.should_exit = True
    running.result(STOP_TIMEOUT)


def until_interrupted() -> None:
    """Block the calling thread until Ctrl+C."""
    # a short sleep rather than a wait on an event, which Ctrl+C cannot end on Windows
    with suppress(KeyboardInterrupt):
        while True:
            time.sleep(0.5)
