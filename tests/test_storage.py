"""A session reads its storage section and hands its devices one path provider."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from ophyd_async.core import Device, PathProvider
from psygnal import Signal

from redsun import AsDevice, AsPresenter, Session
from redsun.path_provider import SessionPathProvider

if TYPE_CHECKING:
    from pathlib import Path

    from .conftest import BuildSession


class Writer(Device):
    """Device writing where the session says."""

    def __init__(self, path_provider: PathProvider, name: str = "") -> None:
        self.path_provider = path_provider
        super().__init__(name=name)


class Announcer:
    """Presenter announcing the plan that is about to run."""

    sig_plan = Signal(str)

    def __init__(self, name: str) -> None:
        self.name = name


class Locating:
    """Presenter asking the session for its path provider by type."""

    def __init__(self, name: str, *, provider: SessionPathProvider) -> None:
        self.name = name
        self.provider = provider


class WriterApp(Session):
    writer: AsDevice[Writer]


class AnnouncerApp(Session):
    announcer: AsPresenter[Announcer]


class LocatingApp(Session):
    locating: AsPresenter[Locating]


def test_a_device_taking_one_gets_the_sessions_provider(build: BuildSession) -> None:
    app = build(WriterApp, {"session": "its-own-session"})

    provider = app.writer.path_provider

    assert provider is app.path_provider
    assert provider().directory_path.parent.name == "its-own-session"


def test_the_root_comes_from_the_storage_section(
    build: BuildSession, tmp_path: Path
) -> None:
    config = {"storage": {"base_dir": str(tmp_path / "elsewhere"), "max_digits": 3}}

    app = build(WriterApp, config)

    assert app.path_provider.base_dir == tmp_path / "elsewhere"
    assert app.storage.max_digits == 3
    assert app.path_provider("det").filename == "unknown_000"


@pytest.mark.parametrize(
    ("config", "error", "match"),
    [
        (
            {"devices": {"writer": {"path_provider": "x"}}},
            TypeError,
            "reserves for the session",
        ),
        ({"storage": {"base_dirs": "x"}}, ValueError, "base_dirs"),
        (
            {"storage": {"catalog": {"readable": "/data"}}},
            ValueError,
            "catalog.readable",
        ),
    ],
    ids=["configured-provider", "unknown-storage-key", "readable-not-a-list"],
)
def test_a_malformed_storage_setting_is_refused(
    build: BuildSession, config: dict[str, Any], error: type[Exception], match: str
) -> None:
    with pytest.raises(error, match=match):
        build(WriterApp, config)


def test_a_catalog_is_refused_without_the_extra(
    build: BuildSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)

    with pytest.raises(RuntimeError, match=r"redsun\[tiled\]"):
        build(WriterApp, {"storage": {"catalog": None}})


def test_a_component_named_path_provider_is_refused(build: BuildSession) -> None:
    class Shadowing(Session):
        path_provider: AsPresenter[Announcer]  # type: ignore[assignment]

    with pytest.raises(TypeError, match="already an attribute of the session"):
        build(Shadowing)


def test_a_presenter_receives_the_provider_by_type(build: BuildSession) -> None:
    app = build(LocatingApp)

    assert app.locating.provider is app.path_provider


def test_the_wiring_reaches_the_provider(build: BuildSession) -> None:
    rules = [{"from": "announcer.sig_plan", "to": "path_provider.set_plan"}]
    app = build(AnnouncerApp, {"wiring": rules})

    app.announcer.sig_plan.emit("square_scan")

    assert app.path_provider("det").filename == "square_scan_00000"
