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

    from redsun.testing import BuildSession


class Writer(Device):
    """Device writing where the session says."""

    def __init__(self, path_provider: PathProvider, name: str = "") -> None:
        self.path_provider = path_provider
        super().__init__(name=name)


class PositionalWriter(Device):
    """A device taking the provider by position only, which the session cannot pass."""

    def __init__(
        self, path_provider: PathProvider | None = None, /, name: str = ""
    ) -> None:
        self.provider = path_provider
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


class PositionalWriterApp(Session):
    writer: AsDevice[PositionalWriter]


class AnnouncerApp(Session):
    announcer: AsPresenter[Announcer]


class LocatingApp(Session):
    locating: AsPresenter[Locating]


def test_a_device_taking_one_gets_the_sessions_provider(build: BuildSession) -> None:
    """Give a device taking a path provider the session's own provider."""
    app = build(WriterApp, {"session": "its-own-session"})

    provider = app.writer.path_provider

    assert provider is app.path_provider
    assert provider().directory_path.parent.name == "its-own-session"


def test_a_device_taking_the_provider_by_position_only_is_skipped(
    build: BuildSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Skip a device that takes `path_provider` by position only, naming why."""
    app = build(PositionalWriterApp)
    assert "writer" not in app.devices
    assert "takes 'path_provider' by position only" in caplog.text


def test_the_root_comes_from_the_storage_section(
    build: BuildSession, tmp_path: Path
) -> None:
    """Take the storage root and file number width from the storage section."""
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
    """Refuse a malformed storage setting or a configured path provider."""
    with pytest.raises(error, match=match):
        build(WriterApp, config)


def test_a_catalog_is_refused_without_the_extra(
    build: BuildSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse a catalog when the `tiled` extra is not installed."""
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)

    with pytest.raises(RuntimeError, match=r"redsun\[tiled\]"):
        build(WriterApp, {"storage": {"catalog": None}})


def test_a_component_named_path_provider_is_refused(build: BuildSession) -> None:
    """Refuse a component named `path_provider`."""

    class Shadowing(Session):
        path_provider: AsPresenter[Announcer]  # type: ignore[assignment]

    with pytest.raises(TypeError, match="already an attribute of the session"):
        build(Shadowing)


def test_a_presenter_receives_the_provider_by_type(build: BuildSession) -> None:
    """Give a presenter the session's path provider when it asks by type."""
    app = build(LocatingApp)

    assert app.locating.provider is app.path_provider


def test_the_wiring_reaches_the_provider(build: BuildSession) -> None:
    """Connect a wiring rule to a slot of the path provider."""
    wiring = {"announcer.sig_plan": "path_provider.set_plan"}
    app = build(AnnouncerApp, {"wiring": wiring})

    app.announcer.sig_plan.emit("square_scan")

    assert app.path_provider("det").filename == "square_scan_00000"
