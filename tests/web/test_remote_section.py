"""Tests for the `remote` section and the sections another frontend owns."""

from __future__ import annotations

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
    """Stands in for `uvicorn.Server`, keeping the configuration it was given."""

    def __init__(self, config: uvicorn.Config, seen: list[uvicorn.Config]) -> None:
        seen.append(config)
        self.config = config
        self.started = True
        self.should_exit = False

    async def serve(self) -> None:
        """Return at once, as a server that has stopped."""


@pytest.fixture
def configs(monkeypatch: pytest.MonkeyPatch) -> list[uvicorn.Config]:
    """Return the configurations `serve` gives to a server, which does not run."""
    seen: list[uvicorn.Config] = []

    def served(config: uvicorn.Config) -> Served:
        return Served(config, seen)

    monkeypatch.setattr(uvicorn, "Server", served)
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
    configs: list[uvicorn.Config], given: dict[str, Any], host: str, port: int
) -> None:
    """Serve where the class says, with each key the file gives replacing the class's."""
    with pytest.raises(SystemExit):
        Placed(given).serve()
    assert [(c.host, c.port) for c in configs] == [(host, port)]


def test_a_session_serves_on_localhost_8000_by_default(
    configs: list[uvicorn.Config],
) -> None:
    """Serve on 127.0.0.1:8000 when nothing sets `remote`."""
    with pytest.raises(SystemExit):
        FastAPISession().serve()
    assert [(c.host, c.port) for c in configs] == [("127.0.0.1", 8000)]


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
