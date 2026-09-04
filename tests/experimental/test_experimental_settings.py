"""Tests for the preferences a session keeps between runs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from app_model import Action
from qtpy.QtWidgets import QApplication

from redsun.experimental import AppContainer, AsPresenter, Settings
from redsun.experimental.containers.qt import QtAppContainer

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


class Recorder:
    """A presenter, so a session has something to build."""

    def __init__(self, name: str, /) -> None:
        self.name = name


class App(AppContainer):
    __slots__ = ()

    config: ClassVar[dict[str, Any]] = {"name": "settings-session"}

    recorder: AsPresenter[Recorder]


class QtApp(QtAppContainer):
    __slots__ = ()

    config: ClassVar[dict[str, Any]] = {"name": "settings-qt-session"}


def test_reading_a_session_that_has_written_nothing_gives_the_default(
    tmp_path: Path,
) -> None:
    """A first run has no file, and asking for a preference must still work."""
    settings = Settings(tmp_path / "absent.json")
    assert settings.get("ask_on_close", True) is True
    assert "ask_on_close" not in settings
    assert not settings.path.exists()


def test_what_is_set_survives_the_session_that_set_it(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "session.json"
    Settings(path).set("ask_on_close", False)

    assert Settings(path).get("ask_on_close", True) is False
    assert list(Settings(path)) == ["ask_on_close"]


def test_a_file_that_cannot_be_read_leaves_the_session_on_defaults(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """It is written by the program, so damage to it must not stop a session."""
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    settings = Settings(path)
    assert settings.get("ask_on_close", True) is True
    assert "Ignoring unreadable settings" in caplog.text


def test_a_file_holding_something_other_than_an_object_is_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Valid JSON is not enough; the keys have to be somewhere."""
    (tmp_path / "list.json").write_text("[1, 2]", encoding="utf-8")

    assert Settings(tmp_path / "list.json").get("anything") is None
    assert "expected an object" in caplog.text


def test_a_value_the_file_cannot_hold_is_refused(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        Settings(tmp_path / "settings.json").set("window", object())


def test_a_session_opens_its_own_only_once_it_is_built(
    config_home: Path, build: Callable[..., AppContainer]
) -> None:
    with pytest.raises(RuntimeError, match=r"Call build\(\) before"):
        _ = App().settings

    assert build(App).settings.path == config_home / "settings-session.json"


@pytest.mark.qt
def test_an_action_asks_for_the_settings_by_type(
    qapp: QApplication, config_home: Path, build: Callable[..., AppContainer]
) -> None:
    seen: list[Settings] = []

    def remember(settings: Settings) -> None:
        seen.append(settings)

    session = build(QtApp)
    session.model.register_action(
        Action(id="probe.settings", title="Settings", callback=remember)
    )

    session.model.commands.execute_command("probe.settings")

    assert seen == [session.settings]
