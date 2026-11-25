"""Tests for the built-in positioner and light presenters served over the web."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from redsun import AsDevice, AsPresenter, Session
from redsun.examples._devices import Laser, Stage
from redsun.fastapi import FastAPISession
from redsun.presenter import LightPresenter, PositionerPresenter

if TYPE_CHECKING:
    from redsun.testing import BuildSession


class Core(Session):
    stage: AsDevice[Stage]
    laser: AsDevice[Laser]
    positioner: AsPresenter[PositionerPresenter]
    lights: AsPresenter[LightPresenter]


class OnWeb(FastAPISession, Core):
    pass


def test_a_move_reports_its_readback(build: BuildSession) -> None:
    """Deliver the signals of a move, readback included, to the WebSocket."""
    session = build(OnWeb)
    with (
        TestClient(session.app) as client,
        client.websocket_connect("/api/events") as events,
    ):
        r = client.post(
            "/api/positioner/move", json={"device": "stage", "axis": "x", "delta": 0.5}
        )
        assert r.status_code == 200
        seen: list[tuple[str, list[object]]] = []
        for _ in range(20):
            message = events.receive_json()
            seen.append((message["signal"], message["args"]))
            if [name for name, _ in seen].count("sig_moving") == 2:
                break
        signals = [name for name, _ in seen]
        assert signals[0] == "sig_moving"
        assert ("sig_readback", ["stage", "x", 0.5]) in seen
        assert signals[-1] == "sig_moving"


def test_the_queries_return_axes_and_lights(build: BuildSession) -> None:
    """Return the axes and the lights with their units."""
    session = build(OnWeb)
    with TestClient(session.app) as client:
        axes = client.get("/api/positioner/axes")
        lights = client.get("/api/lights/lights")
    assert (axes.status_code, lights.status_code) == (200, 200)
    assert axes.json()["stage"]["x"]["readback"]["units"] == "um"
    assert lights.json()["laser"]["intensity"]["units"] == "mW"


def test_locks_and_configuration_are_not_served(build: BuildSession) -> None:
    """Leave set_locked and configure out of the API."""
    session = build(OnWeb)
    with TestClient(session.app) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert not [p for p in paths if "set_locked" in p or "configure" in p]


def test_move_to_takes_a_mapping(build: BuildSession) -> None:
    """Accept a mapping of axis names to targets."""
    session = build(OnWeb)
    with TestClient(session.app) as client:
        r = client.post(
            "/api/positioner/move_to",
            json={"device": "stage", "positions": {"x": 1.0}},
        )
    assert r.status_code == 200
