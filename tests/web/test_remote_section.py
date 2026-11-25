"""Tests for the `remote` section and the sections another frontend owns."""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
import uvicorn
from fastapi.testclient import TestClient

from redsun import ConfigurationError, Session
from redsun._config import RemoteConfig
from redsun.fastapi import FastAPISession, RemoteSettings
from tests.sdk.compute.test_settings import mirrored
from tests.web.test_fastapi_session import OnWeb

if TYPE_CHECKING:
    from pathlib import Path

    from redsun.testing import BuildSession

ORIGIN = "http://localhost:5173"

VIEW = {"plugin_name": "mock-bundle", "plugin_id": "mock-motor-view"}


class Placed(FastAPISession):
    remote: ClassVar[RemoteSettings] = {"host": "0.0.0.0", "port": 9000}


class Served:
    """Stands in for `uvicorn.Server`, a server that stops at once."""

    def __init__(self, config: uvicorn.Config) -> None:
        self.config = config
        self.should_exit = False

    async def serve(self, sockets: list[socket.socket]) -> None:
        """Return at once, as a server that has stopped."""


@pytest.fixture
def addresses(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    """Return the addresses `serve` binds, binding a free port instead and running no server."""
    seen: list[tuple[str, int]] = []

    def bind(address: tuple[str, int], **kwargs: object) -> socket.socket:
        seen.append(address)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        return sock

    monkeypatch.setattr(socket, "create_server", bind)
    monkeypatch.setattr(uvicorn, "Server", Served)
    monkeypatch.setattr("redsun.fastapi._session.until_interrupted", lambda: None)
    return seen


@pytest.mark.usefixtures("mock_plugin")
def test_a_file_alone_builds_a_web_session(
    config_path: Path, build: BuildSession
) -> None:
    """Build a FastAPISession from a file naming the frontend, and serve its presenter."""
    session = build(Session.from_config(str(config_path / "web_session.yaml")))
    assert isinstance(session, FastAPISession)
    assert "/api/mover/position" in session.app.openapi()["paths"]


@pytest.mark.parametrize(
    ("given", "host", "port"),
    [
        ({"remote": {"port": 9100}}, "0.0.0.0", 9100),
        ({}, "0.0.0.0", 9000),
    ],
)
def test_the_file_lays_over_the_class_key_by_key(
    addresses: list[tuple[str, int]], given: dict[str, Any], host: str, port: int
) -> None:
    """Serve where the class says, with each key the file gives replacing the class's."""
    with pytest.raises(SystemExit):
        Placed(given).serve()
    assert addresses == [(host, port)]


def test_a_session_serves_on_localhost_8000_by_default(
    addresses: list[tuple[str, int]],
) -> None:
    """Serve on 127.0.0.1:8000 when nothing sets `remote`."""
    with pytest.raises(SystemExit):
        FastAPISession().serve()
    assert addresses == [("127.0.0.1", 8000)]


@pytest.mark.parametrize(
    ("session", "config", "section"),
    [
        (Session, {"remote": {"port": 1}}, "remote"),
        (OnWeb, {"views": {"panel": VIEW}}, "views"),
        (OnWeb, {"shortcuts": {"mover.move": "Ctrl+M"}}, "shortcuts"),
        (OnWeb, {"actions": [{"text": "Move"}]}, "actions"),
        (OnWeb, {"color_scheme": "dark"}, "color_scheme"),
    ],
)
def test_a_section_owned_by_another_frontend_is_refused(
    build: BuildSession,
    session: type[Session],
    config: dict[str, Any],
    section: str,
) -> None:
    """Raise a ConfigurationError naming a section the session's frontend does not read."""
    with pytest.raises(ConfigurationError, match=f"{section}: .* does not read"):
        build(session, config)


def test_the_typed_dict_mirrors_the_model() -> None:
    """Keep RemoteSettings and RemoteConfig in step, key by key and type by type."""
    assert mirrored(RemoteSettings, RemoteConfig) == []


@pytest.mark.parametrize(("origins", "allowed"), [([ORIGIN], ORIGIN), ([], None)])
def test_an_origin_is_allowed_by_cors(
    build: BuildSession, origins: list[str], allowed: str | None
) -> None:
    """Answer a preflight from a listed origin with its allow header, and others without."""
    session = build(OnWeb, {"remote": {"origins": origins}})
    with TestClient(session.app) as client:
        r = client.options(
            "/api/mover/position",
            headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"},
        )
    assert r.headers.get("access-control-allow-origin") == allowed
