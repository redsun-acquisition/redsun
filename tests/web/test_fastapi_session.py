"""Tests for a session serving its presenters over HTTP and a WebSocket."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from psygnal import Signal

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

if TYPE_CHECKING:
    from redsun.testing import BuildSession


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
