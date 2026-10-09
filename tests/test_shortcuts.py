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
