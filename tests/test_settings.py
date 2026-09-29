"""Tests for the preferences a session keeps between runs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from app_model import Action
from qtpy.QtWidgets import QApplication

from redsun import AsPresenter, Session, Settings
from redsun.qt import QtSession

if TYPE_CHECKING:
    from pathlib import Path

    from .conftest import BuildSession


class Recorder:
    """A presenter, so a session has something to build."""

    def __init__(self, name: str) -> None:
        self.name = name


class App(Session):
    config: ClassVar[dict[str, Any]] = {"session": "settings-session"}

    recorder: AsPresenter[Recorder]


class QtApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "settings-qt-session"}


def test_reading_a_session_that_has_written_nothing_gives_the_default(
    tmp_path: Path,
) -> None:
    """Return the default for a preference when no settings file exists yet."""
    settings = Settings(tmp_path / "absent.json")
    assert settings.get("ask_on_close", True) is True
    assert "ask_on_close" not in settings
    assert not settings.path.exists()


def test_what_is_set_survives_the_session_that_set_it(tmp_path: Path) -> None:
    """Keep a preference for later sessions reading the same file."""
    path = tmp_path / "nested" / "session.json"
    Settings(path).set("ask_on_close", False)

    assert Settings(path).get("ask_on_close", True) is False
    assert list(Settings(path)) == ["ask_on_close"]


def test_a_file_that_cannot_be_read_leaves_the_session_on_defaults(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Log and ignore a settings file that is not valid JSON, returning defaults."""
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    settings = Settings(path)
    assert settings.get("ask_on_close", True) is True
    assert "Ignoring unreadable settings" in caplog.text


def test_a_file_holding_something_other_than_an_object_is_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Ignore a settings file whose JSON is not an object, and log why."""
    (tmp_path / "list.json").write_text("[1, 2]", encoding="utf-8")

    assert Settings(tmp_path / "list.json").get("anything") is None
    assert "expected an object" in caplog.text


def test_a_value_the_file_cannot_hold_is_refused(tmp_path: Path) -> None:
    """Refuse to set a value JSON cannot hold."""
    with pytest.raises(TypeError):
        # a type checker refuses it too; this pins the refusal for untyped callers
        Settings(tmp_path / "settings.json").set("window", object())  # type: ignore[arg-type]


def test_a_session_opens_its_own_only_once_it_is_built(
    config_home: Path, build: BuildSession
) -> None:
    """Open the settings file of a session only once the session is built."""
    with pytest.raises(RuntimeError, match=r"Call build\(\) before"):
        _ = App().settings

    assert build(App).settings.path == config_home / "settings-session.json"


@pytest.mark.qt
def test_an_action_asks_for_the_settings_by_type(
    qapp: QApplication, config_home: Path, build: BuildSession
) -> None:
    """Pass the session's settings to an action callback asking for them by type."""
    seen: list[Settings] = []

    def remember(settings: Settings) -> None:
        seen.append(settings)

    session = build(QtApp)
    session.model.register_action(
        Action(id="probe.settings", title="Settings", callback=remember)
    )

    session.model.commands.execute_command("probe.settings")

    assert seen == [session.settings]
