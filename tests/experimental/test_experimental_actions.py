"""Tests for the ``actions`` section of an experimental Qt session."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app_model import Application
from mock_bundle import actions
from qtpy.QtWidgets import QApplication, QMenu

from redsun.experimental import Session
from redsun.experimental.session.qt import ActionError, QtSession

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

pytestmark = pytest.mark.qt

SESSION = {"frontend": "pyqt", "name": "actions-session"}


@pytest.fixture(autouse=True)
def clear_record() -> Iterator[None]:
    """Forget what earlier commands recorded, the module list outliving a test."""
    actions.executed.clear()
    yield
    actions.executed.clear()


def session(*declared: dict[str, object]) -> QtSession:
    """Return an unbuilt Qt session declaring *declared* under ``actions``."""
    container = Session.from_config({**SESSION, "actions": list(declared)})
    assert isinstance(container, QtSession)
    return container


def test_the_section_registers_commands_on_the_session(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    app = build(
        session(
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
        )
    )

    app.model.commands.execute_command("probe.note")
    app.model.commands.execute_command("probe.twice")
    menu_bar = app.main_window.setModelMenuBar({"probe/tools": "Tools"})
    tools = next(m for m in menu_bar.findChildren(QMenu) if m.title() == "Tools")

    assert actions.executed == ["note", "twice", "twice"]
    assert [entry.text() for entry in tools.actions()] == ["Note"]


def test_releasing_the_session_takes_its_commands_with_it(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    app = build(
        session(
            {
                "id": "probe.note",
                "title": "Note",
                "callback": "mock_bundle.actions:note",
            }
        )
    )
    model = app.model
    model.commands.execute_command("probe.note")
    assert actions.executed == ["note"]

    app.shutdown()

    with pytest.raises(KeyError, match="probe.note"):
        model.commands.execute_command("probe.note")


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
    qapp: QApplication, declared: object, message: str
) -> None:
    app = Session.from_config({**SESSION, "actions": declared})
    with pytest.raises(ActionError, match=message):
        app.build()
    assert Application.get_app("actions-session") is None
