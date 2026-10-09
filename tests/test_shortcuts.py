"""Tests for the keyboard shortcuts a session collects, in its class or its file."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from redsun import (
    AsPresenter,
    AsView,
    BuildError,
    ConfigurationError,
    Frontend,
    Placement,
    Session,
    shortcut,
)

if TYPE_CHECKING:
    from redsun.testing import BuildSession


@dataclass(frozen=True)
class Spot(Placement):
    """A placement the toy frontend attaches."""

    region: str


class Toy(Frontend):
    """A frontend that reads every key except one holding a question mark."""

    @classmethod
    def key_problems(cls, key: str) -> list[str]:
        return [f"{key!r} holds a question mark"] if "?" in key else []


class Panel:
    """A view with a window key and a key of its own."""

    placement: Placement = Spot("left")

    def __init__(self, name: str) -> None:
        self.name = name

    @shortcut("Ctrl+R", title="Run")
    def run(self) -> None: ...

    @shortcut("Escape", title="Stop", scope="view")
    def stop(self) -> None: ...


class Controller:
    """A presenter asking for the view's window key."""

    def __init__(self, name: str) -> None:
        self.name = name

    @shortcut("Ctrl+R", title="Restart")
    def restart(self) -> None: ...


class ToyApp(Session):
    """A view and a presenter whose keys meet."""

    frontend = Toy
    config: ClassVar[dict[str, Any]] = {"session": "toy-shortcuts"}

    panel: AsView[Panel]
    controller: AsPresenter[Controller]


def test_the_session_file_replaces_and_drops_keys(build: BuildSession) -> None:
    """Replace a command's key from the file, and drop one given null."""
    app = build(
        ToyApp, {"shortcuts": {"panel.run": "Ctrl+Shift+R", "panel.stop": None}}
    )

    keys = {b.command: b.keys for b in app.resolve_shortcuts()}

    assert keys["panel.run"] == ("Ctrl+Shift+R",)
    assert keys["panel.stop"] == ()


def test_a_conflict_is_logged_naming_both(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Log a key two components ask for, naming both, the first declared keeping it."""
    app = build(ToyApp)
    caplog.set_level(logging.WARNING, logger="redsun")

    keys = {b.command: b.keys for b in app.resolve_shortcuts()}

    assert keys == {
        "panel.run": ("Ctrl+R",),
        "panel.stop": ("Escape",),
        "controller.restart": (),
    }
    assert "Ctrl+R: kept on panel.run, taken from controller.restart" in caplog.text


def test_a_strict_session_refuses_a_conflict(build: BuildSession) -> None:
    """Raise BuildError for a conflict when the configuration sets strict."""
    app = build(ToyApp, {"strict": True})

    with pytest.raises(BuildError, match="kept on panel.run"):
        app.resolve_shortcuts()


def test_a_key_the_frontend_cannot_read_is_refused(build: BuildSession) -> None:
    """Refuse a file key the frontend cannot read, naming the command, before anything is built."""
    with pytest.raises(ConfigurationError, match=r"shortcuts\.panel\.run"):
        build(ToyApp, {"shortcuts": {"panel.run": "Ctrl+?"}})


def test_a_file_key_list_holds_at_most_two(build: BuildSession) -> None:
    """Refuse a command given three keys in the file."""
    with pytest.raises(ConfigurationError, match="two at most"):
        build(ToyApp, {"shortcuts": {"panel.run": ["F1", "F2", "F3"]}})


def test_the_shortcuts_section_is_written_back(build: BuildSession) -> None:
    """Write the file's shortcuts section into the serialized configuration."""
    section = {"panel.run": ["F1", "F2"], "panel.stop": None}

    app = build(ToyApp, {"shortcuts": section})

    assert app.serialize()["shortcuts"] == section


def test_saved_keys_apply_over_the_session_file_until_reset(
    build: BuildSession,
) -> None:
    """Apply a saved key over the session file's, and the file's again after a reset."""
    app = build(ToyApp, {"shortcuts": {"panel.run": "F1"}})

    app.set_shortcuts({"panel.run": ["F9"], "panel.stop": []})
    saved = {b.command: b.keys for b in app.resolve_shortcuts()}
    stored = app.settings.get("shortcuts")
    app.reset_shortcuts()
    reset = {b.command: b.keys for b in app.resolve_shortcuts()}

    assert (saved["panel.run"], saved["panel.stop"]) == (("F9",), ())
    assert stored == {"panel.run": ["F9"], "panel.stop": []}
    assert (reset["panel.run"], reset["panel.stop"]) == (("F1",), ("Escape",))


def test_a_stolen_key_stays_stolen_in_a_second_session(build: BuildSession) -> None:
    """Keep a key moved to a later command there in the next session built."""
    first = build(ToyApp)
    first.set_shortcuts({"controller.restart": ["Ctrl+R"], "panel.run": []})
    first.shutdown()

    second = build(ToyApp)
    keys = {b.command: b.keys for b in second.resolve_shortcuts()}

    assert (keys["panel.run"], keys["controller.restart"]) == ((), ("Ctrl+R",))


def test_saved_keys_the_session_cannot_use_are_logged_once_and_kept(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Log a saved command the session lacks and a key it can't read once, keep them in the file, and build under strict."""
    app = build(ToyApp, {"strict": True, "shortcuts": {"controller.restart": "F3"}})
    app.settings.set(
        "shortcuts", {"gone.thing": ["F1"], "panel.run": ["Ctrl+?"], "panel.stop": 3}
    )

    with caplog.at_level(logging.WARNING, logger="redsun"):
        first = {b.command: b.keys for b in app.resolve_shortcuts()}
        app.resolve_shortcuts()
    app.set_shortcuts({"panel.stop": ["F2"]})

    assert first["panel.run"] == ("Ctrl+R",)
    assert caplog.text.count("gone.thing") == 1
    assert caplog.text.count("Ctrl+?") == 1
    assert app.settings.get("shortcuts")["gone.thing"] == ["F1"]


@pytest.mark.parametrize(
    "keys", [["Ctrl+?"], ["F1", "F2", "F3"]], ids=["unreadable", "three"]
)
def test_setting_a_key_the_session_cannot_keep_is_refused(
    build: BuildSession, keys: list[str]
) -> None:
    """Refuse a key the frontend can't read, and more than two keys, saving nothing."""
    app = build(ToyApp)

    with pytest.raises(ValueError, match="panel.run"):
        app.set_shortcuts({"panel.run": keys})

    assert "shortcuts" not in app.settings


def test_a_saved_key_taking_a_default_does_not_stop_a_strict_session(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Give a saved key to its command over an earlier default, and only log it under strict."""
    app = build(ToyApp, {"strict": True, "shortcuts": {"controller.restart": "F3"}})
    app.set_shortcuts({"controller.restart": ["Ctrl+R"]})

    with caplog.at_level(logging.WARNING, logger="redsun"):
        keys = {b.command: b.keys for b in app.resolve_shortcuts()}

    assert (keys["panel.run"], keys["controller.restart"]) == ((), ("Ctrl+R",))
    assert "kept on controller.restart, taken from panel.run" in caplog.text
