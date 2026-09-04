"""Tests for the ``actions`` section of an experimental Qt session."""

from __future__ import annotations

from typing import Any

import pytest
from app_model import Application
from mock_bundle import actions
from qtpy.QtWidgets import QMenu

from redsun.experimental import AppContainer
from redsun.experimental.containers.qt import ActionError, QtAppContainer

pytestmark = pytest.mark.qt

SESSION = {"frontend": "pyqt", "name": "actions-session"}


@pytest.fixture(autouse=True)
def clear_record() -> Any:
    """Forget what earlier commands recorded, the module list outliving a test."""
    actions.executed.clear()
    yield
    actions.executed.clear()


def session(*declared: dict[str, Any]) -> QtAppContainer:
    """Return an unbuilt Qt session declaring *declared* under ``actions``."""
    container = AppContainer.from_config({**SESSION, "actions": list(declared)})
    assert isinstance(container, QtAppContainer)
    return container


def test_the_section_registers_commands_on_the_session(qapp: Any) -> None:
    """A session's contributions are read from its file and run against it."""
    app = session(
        {
            "id": "probe.note",
            "title": "Note",
            "callback": "mock_bundle.actions:note",
            "menus": [{"id": "probe/tools"}],
        },
        {
            "id": "probe.twice",
            "title": "Twice",
            "callback": "mock_bundle.actions:note_twice",
        },
    ).build()
    try:
        app.model.commands.execute_command("probe.note")
        app.model.commands.execute_command("probe.twice")
        assert actions.executed == ["note", "twice", "twice"]

        menu_bar = app.main_window.setModelMenuBar({"probe/tools": "Tools"})
        tools = next(m for m in menu_bar.findChildren(QMenu) if m.title() == "Tools")
        assert [entry.text() for entry in tools.actions()] == ["Note"]
    finally:
        app.shutdown()


def test_releasing_the_session_takes_its_commands_with_it(qapp: Any) -> None:
    """The disposer is held for release, so the registry does not outlive it."""
    app = session(
        {"id": "probe.note", "title": "Note", "callback": "mock_bundle.actions:note"}
    ).build()
    try:
        app.model.commands.execute_command("probe.note")
        assert actions.executed == ["note"]

        app.virtual_container.release()
        with pytest.raises(KeyError, match="probe.note"):
            app.model.commands.execute_command("probe.note")
    finally:
        app.shutdown()


@pytest.mark.parametrize(
    ("declared", "message"),
    [
        pytest.param(
            "mock_bundle.actions:note", "must be a list of entries", id="not-a-list"
        ),
        pytest.param([["probe.note"]], "must be a mapping", id="entry-not-a-mapping"),
        pytest.param(
            [
                {
                    "id": "probe.note",
                    "title": "Note",
                    "callback": "mock_bundle.actions:note",
                    "menu": "probe/tools",
                }
            ],
            r"unknown key\(s\) menu",
            id="unknown-key",
        ),
        pytest.param([{"id": "probe.note"}], "is not an action", id="missing-field"),
        pytest.param(
            [{"id": "probe.note", "title": "Note", "callback": "note"}],
            "is not an action",
            id="callback-not-a-python-name",
        ),
    ],
)
def test_a_section_that_is_not_actions_is_refused(
    qapp: Any, declared: Any, message: str
) -> None:
    """A contribution that cannot be made is loud, and frees the name it took."""
    app = AppContainer.from_config({**SESSION, "actions": declared})
    with pytest.raises(ActionError, match=message):
        app.build()
    assert Application.get_app("actions-session") is None
