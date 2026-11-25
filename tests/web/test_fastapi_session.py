"""Tests for a session serving its presenters over HTTP and a WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from concurrent.futures import Future
from typing import TYPE_CHECKING, Annotated, Any, TypeVarTuple

import httpx
import pytest
import uvicorn
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from psygnal import Signal
from pydantic import Field
from websockets.sync.client import connect

from redsun import (
    AsPresenter,
    AsView,
    BuildError,
    Placement,
    Session,
    WebSession,
    remote,
    slot,
)
from redsun.fastapi import FastAPISession
from redsun.fastapi._session import stop

if TYPE_CHECKING:
    from collections.abc import Callable, MutableMapping
    from contextvars import Context

    from redsun.testing import BuildSession

Ts = TypeVarTuple("Ts")


class Mover:
    sig_moved = Signal(float)
    sig_any = Signal(object)

    def __init__(self, name: str) -> None:
        self.name = name
        self.at = 0.0

    @property
    @remote
    def position(self) -> float:
        return self.at

    @property
    @remote
    def broken(self) -> float:
        raise RuntimeError("no reading")

    @slot
    @remote
    async def move(self, delta: float) -> float:
        self.at += delta
        self.sig_moved.emit(self.at)
        return self.at

    @slot
    @remote
    async def fail(self) -> None:
        raise RuntimeError("motor stalled")

    @slot
    async def calibrate(self) -> None:
        self.at = 0.0


class Broken:
    def __init__(self, name: str) -> None:
        self.name = name

    @slot
    @remote
    def go(self) -> None: ...


class Twice:
    def __init__(self, name: str) -> None:
        self.name = name

    @slot(name="go")
    @remote
    async def first(self) -> None: ...

    @slot(name="go")
    @remote
    async def second(self) -> None: ...


class Misnamed:
    def __init__(self, name: str) -> None:
        self.name = name

    @slot
    @remote
    async def configure(self, model_config: float) -> None: ...

    @slot
    @remote
    async def nudge(self, _delta: float) -> None: ...


class Bounded:
    def __init__(self, name: str) -> None:
        self.name = name
        self.at = 0.0

    @slot
    @remote
    async def move(self, delta: Annotated[float, Field(ge=0)]) -> float:
        self.at += delta
        return self.at


class Ending:
    def __init__(self, name: str) -> None:
        self.name = name

    @slot
    @remote
    async def c(self) -> None: ...


class Starting:
    def __init__(self, name: str) -> None:
        self.name = name

    @slot
    @remote
    async def b_c(self) -> None: ...


def free_port() -> int:
    """Return a port nothing listens on."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class ClosedLoop(asyncio.SelectorEventLoop):
    """A loop refusing work from other threads, as a closed one does, while `refusing` is set."""

    def __init__(self) -> None:
        super().__init__()
        self.refusing = False

    def call_soon_threadsafe(
        self,
        callback: Callable[[*Ts], object],
        *args: *Ts,
        context: Context | None = None,
    ) -> asyncio.Handle:
        if self.refusing:
            raise RuntimeError("Event loop is closed")
        return super().call_soon_threadsafe(callback, *args, context=context)


class MyView:
    placement = Placement()

    def __init__(self, name: str) -> None:
        self.name = name


class Core(Session):
    mover: AsPresenter[Mover]
    broken: AsPresenter[Broken]


class OnWeb(FastAPISession, Core):
    pass


class WithView(OnWeb):
    panel: AsView[MyView]


class Doubled(FastAPISession):
    twice: AsPresenter[Twice]


class WithMisnamed(FastAPISession):
    misnamed: AsPresenter[Misnamed]


class WithBounded(FastAPISession):
    bounded: AsPresenter[Bounded]


class Joined(FastAPISession):
    a_b: AsPresenter[Ending]
    a: AsPresenter[Starting]


def test_a_command_answers_and_its_signal_reaches_the_websocket(
    build: BuildSession,
) -> None:
    """Return a command's value and deliver the signal it emits."""
    session = build(OnWeb)
    with (
        TestClient(session.app) as client,
        client.websocket_connect("/api/events") as events,
    ):
        r = client.post("/api/mover/move", json={"delta": 0.5})
        assert (r.status_code, r.json()) == (200, 0.5)
        assert events.receive_json() == {
            "presenter": "mover",
            "signal": "sig_moved",
            "args": [0.5],
        }


def test_a_query_returns_the_property(build: BuildSession) -> None:
    """Answer a remote property's value."""
    session = build(OnWeb)
    with TestClient(session.app) as client:
        r = client.get("/api/mover/position")
    assert (r.status_code, r.json()) == (200, 0.0)


def test_a_body_of_the_wrong_type_is_refused_before_the_slot_runs(
    build: BuildSession,
) -> None:
    """Answer 422 to a body of the wrong type, leaving the presenter as it was."""
    session = build(OnWeb)
    with TestClient(session.app) as client:
        r = client.post("/api/mover/move", json={"delta": "far"})
    assert r.status_code == 422
    assert session.mover.position == 0.0


def test_a_body_breaking_a_parameter_constraint_is_refused(
    build: BuildSession,
) -> None:
    """Answer 422 to a value outside an `Annotated` parameter's bounds."""
    session = build(WithBounded)
    with TestClient(session.app) as client:
        r = client.post("/api/bounded/move", json={"delta": -1.0})
    assert r.status_code == 422
    assert session.bounded.at == 0.0


def test_an_unmarked_slot_has_no_route(build: BuildSession) -> None:
    """Answer 404 for a slot not marked remote."""
    session = build(OnWeb)
    with TestClient(session.app) as client:
        r = client.post("/api/mover/calibrate", json={})
    assert r.status_code == 404


def test_a_presenter_breaking_a_rule_is_left_out_but_built(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Keep a presenter served() refuses built, with no route and an error naming the member."""
    with caplog.at_level(logging.ERROR, logger="redsun"):
        session = build(OnWeb)
    assert "broken" in session.presenters
    paths = session.app.openapi()["paths"]
    assert not [path for path in paths if path.startswith("/api/broken/")]
    assert "'go'" in caplog.text


def test_a_strict_session_refuses_a_presenter_left_out_of_the_api(
    build: BuildSession,
) -> None:
    """Raise at the report step of a strict session when a presenter is left out of the API."""
    with pytest.raises(BuildError, match="broken"):
        build(OnWeb, {"strict": True})


def test_two_remote_slots_on_one_port_leave_the_presenter_out(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Leave out a presenter whose remote slots share a port name."""
    with caplog.at_level(logging.ERROR, logger="redsun"):
        session = build(Doubled)
    assert "/api/twice/go" not in session.app.openapi()["paths"]
    assert "'go'" in caplog.text


def test_the_openapi_document_lists_exactly_the_remote_members(
    build: BuildSession,
) -> None:
    """List a route for each remote member and the signals route, nothing else."""
    session = build(OnWeb)
    assert set(session.app.openapi()["paths"]) == {
        "/api/mover/move",
        "/api/mover/fail",
        "/api/mover/position",
        "/api/mover/broken",
        "/api/signals",
    }


def test_the_signals_route_describes_each_signal(build: BuildSession) -> None:
    """Describe each published signal's arguments as JSON Schema."""
    session = build(OnWeb)
    with TestClient(session.app) as client:
        r = client.get("/api/signals")
    assert r.json() == {"mover": {"sig_moved": [{"type": "number"}], "sig_any": [{}]}}


def test_a_fastapi_session_is_a_web_session(build: BuildSession) -> None:
    """Satisfy the web session protocol."""
    session = build(OnWeb)
    assert isinstance(session, WebSession)


def test_a_web_session_refuses_a_declared_view(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Skip a view declared on a web session, saying it has none."""
    session = build(WithView)
    assert "panel" not in session.views
    assert "a web session has no views" in caplog.text


def test_a_closed_websocket_leaves_the_session_running(build: BuildSession) -> None:
    """Keep serving once a client has closed its socket and its loop is gone."""
    session = build(OnWeb)
    with TestClient(session.app) as client, client.websocket_connect("/api/events"):
        pass
    with TestClient(session.app) as client:
        r = client.post("/api/mover/move", json={"delta": 1.0})
    assert (r.status_code, r.json()) == (200, 1.0)


def test_a_slot_that_raises_answers_500_and_the_server_goes_on(
    build: BuildSession,
) -> None:
    """Answer 500 with the exception's text, then serve the next call."""
    session = build(OnWeb)
    with TestClient(session.app) as client:
        failed = client.post("/api/mover/fail", json={})
        moved = client.post("/api/mover/move", json={"delta": 1.0})
    assert failed.status_code == 500
    assert "motor stalled" in failed.json()["error"]
    assert moved.status_code == 200


def test_an_unserialisable_payload_is_dropped_and_later_ones_are_sent(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Drop an emission that cannot be serialised with a warning, and send the next."""
    session = build(OnWeb)
    with (
        caplog.at_level(logging.WARNING, logger="redsun"),
        TestClient(session.app) as client,
        client.websocket_connect("/api/events") as events,
    ):
        session.mover.sig_any.emit(object())
        session.mover.sig_moved.emit(1.0)
        assert events.receive_json()["signal"] == "sig_moved"
    assert "sig_any" in caplog.text


def test_shutdown_with_a_client_connected_closes_its_socket(
    build: BuildSession,
) -> None:
    """Close an open socket when the session shuts down."""
    session = build(OnWeb)
    with (
        TestClient(session.app) as client,
        client.websocket_connect("/api/events") as events,
    ):
        session.shutdown()
        with pytest.raises(WebSocketDisconnect):
            events.receive_json()


def test_a_getter_that_raises_answers_500(build: BuildSession) -> None:
    """Answer 500 with the exception's text when a remote getter raises."""
    session = build(OnWeb)
    with TestClient(session.app) as client:
        r = client.get("/api/mover/broken")
    assert r.status_code == 500
    assert "no reading" in r.json()["error"]


def test_serve_on_a_port_in_use_raises_and_shuts_the_session_down(
    build: BuildSession,
) -> None:
    """Raise when the server cannot start, leaving the session shut down."""
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        session = build(OnWeb, {"remote": {"port": port}})
        with pytest.raises(RuntimeError, match=f"could not start on 127.0.0.1:{port}"):
            session.serve()
    assert not session.is_built


def test_serve_answers_until_interrupted(
    build: BuildSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Answer a request and send an event while serving, then exit with 0 and shut down."""
    port = free_port()
    session = build(OnWeb, {"remote": {"port": port}})
    answers: list[httpx.Response] = []
    events: list[str | bytes] = []

    def interrupted() -> None:
        answers.append(httpx.get(f"http://127.0.0.1:{port}/api/mover/position"))
        with connect(f"ws://127.0.0.1:{port}/api/events", open_timeout=5) as client:
            httpx.post(f"http://127.0.0.1:{port}/api/mover/move", json={"delta": 0.5})
            events.append(client.recv(timeout=5))

    monkeypatch.setattr("redsun.fastapi._session.until_interrupted", interrupted)
    with pytest.raises(SystemExit) as exit_:
        session.serve()
    assert exit_.value.code == 0
    assert [(a.status_code, a.json()) for a in answers] == [(200, 0.0)]
    assert [json.loads(e) for e in events] == [
        {"presenter": "mover", "signal": "sig_moved", "args": [0.5]}
    ]
    assert not session.is_built


def test_the_app_is_released_on_shutdown(build: BuildSession) -> None:
    """Drop the app when the session shuts down, so its routes do not hold presenters."""
    session = build(OnWeb)
    session.shutdown()
    with pytest.raises(RuntimeError, match="build"):
        _ = session.app


def test_a_presenter_left_out_of_the_api_is_not_served(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Summarise a presenter left out of the API as not served, not as not set up."""
    with caplog.at_level(logging.WARNING, logger="redsun"):
        build(OnWeb)
    assert "Not served: broken (presenter)" in caplog.text
    assert "Not set up" not in caplog.text


def test_stop_warns_when_the_server_is_still_running(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Log a warning when the server has not stopped within the timeout."""
    monkeypatch.setattr("redsun.fastapi._session.STOP_TIMEOUT", 0.01)
    server = uvicorn.Server(uvicorn.Config("none:app"))
    with caplog.at_level(logging.WARNING, logger="redsun"):
        stop(server, Future())
    assert "still running" in caplog.text


def test_a_parameter_a_body_cannot_carry_leaves_the_presenter_out(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Leave out a presenter with a parameter named like a model attribute or starting with '_'."""
    with caplog.at_level(logging.ERROR, logger="redsun"):
        session = build(WithMisnamed)
    assert "misnamed" in session.presenters
    paths = session.app.openapi()["paths"]
    assert not [path for path in paths if path.startswith("/api/misnamed/")]
    assert "'model_config'" in caplog.text
    assert "'_delta'" in caplog.text


def test_paths_joining_to_one_name_get_distinct_operation_ids(
    build: BuildSession,
) -> None:
    """Give /api/a_b/c and /api/a/b_c operation ids of their own."""
    session = build(Joined)
    paths = session.app.openapi()["paths"]
    ids = {paths[p]["post"]["operationId"] for p in ("/api/a_b/c", "/api/a/b_c")}
    assert len(ids) == 2


def test_an_emission_with_no_client_is_not_serialised(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Log nothing for an emission no client would receive."""
    session = build(OnWeb)
    with caplog.at_level(logging.WARNING, logger="redsun"):
        session.mover.sig_any.emit(object())
    assert "sig_any" not in caplog.text


def test_an_emission_reaching_a_closed_loop_does_not_reach_the_emitter(
    build: BuildSession,
) -> None:
    """Emit without raising while a connected socket's loop refuses work."""
    session = build(OnWeb)
    loop = ClosedLoop()
    inbox: asyncio.Queue[MutableMapping[str, Any]] = asyncio.Queue()
    accepted = loop.create_future()
    scope: dict[str, Any] = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "scheme": "ws",
        "path": "/api/events",
        "raw_path": b"/api/events",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("test", 1),
        "server": ("test", 80),
        "subprotocols": [],
    }

    async def send(message: MutableMapping[str, Any]) -> None:
        if message["type"] == "websocket.accept":
            accepted.set_result(None)

    inbox.put_nowait({"type": "websocket.connect"})
    handler = loop.create_task(session.app(scope, inbox.get, send))
    try:
        loop.run_until_complete(accepted)
        loop.refusing = True
        session.mover.sig_moved.emit(1.0)
    finally:
        loop.refusing = False
        inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
        loop.run_until_complete(handler)
        loop.close()
