"""Tests for declaring a presenter and its views as one stack."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any

import pytest
from mock_bundle.devices import MockStage
from mock_bundle.presenters import MockMotorPresenter
from mock_bundle.stacks import MockMotorStack
from mock_bundle.views import MockMotorView, Somewhere
from psygnal import Signal

from redsun import (
    AsDevice,
    AsPresenter,
    AsStack,
    AsView,
    ConfigurationError,
    Declare,
    Placement,
    Session,
)

if TYPE_CHECKING:
    from redsun.testing import BuildSession


class Talker:
    """A presenter announcing what it says."""

    sig_said = Signal(str)

    def __init__(self, name: str) -> None:
        self.name = name


class Hearer:
    """A view showing what a talker says."""

    placement: Placement = Somewhere()

    def __init__(self, name: str) -> None:
        self.name = name


class Duo:
    """A talker with its hearer."""

    presenter: AsPresenter[Talker]
    view: AsView[Hearer]


class NoPresenter:
    view: AsView[Hearer]


class TwoPresenters:
    first: AsPresenter[Talker]
    second: AsPresenter[Talker]
    view: AsView[Hearer]


class NoView:
    presenter: AsPresenter[Talker]


class WithDevice:
    presenter: AsPresenter[Talker]
    view: AsView[Hearer]
    stage: AsDevice[MockStage]


class TakesArgument:
    presenter: AsPresenter[Talker]
    view: AsView[Hearer]

    def __init__(self, motor: str) -> None:
        self.motor = motor


class Plugged(Session):
    """Every component comes from the mock bundle."""


class WithDuo(Session):
    duo: AsStack[Duo]


class Clashing(WithDuo):
    duo_view: AsPresenter[Talker]


class Declared(Session):
    motor: AsStack[MockMotorStack]


class DeclaredOver(Session):
    motor: Annotated[AsStack[MockMotorStack], Declare(detail={"title": "class"})]


AsAnyStack: Any = AsStack


def title_of(session: Session, name: str) -> str:
    """Return the title of the view built as *name*."""
    view = session.views[name]
    assert isinstance(view, MockMotorView)
    return view.title


PLUGIN_STACK: dict[str, Any] = {
    "session": "stacks-plugin",
    "providers": {
        "services": {"plugin_name": "mock-bundle", "plugin_id": "mock-services"}
    },
    "devices": {"stage": {"plugin_name": "mock-bundle", "plugin_id": "mock-stage"}},
    "stacks": {"motor": {"plugin_name": "mock-bundle", "plugin_id": "mock-motor"}},
}


def test_a_stack_from_a_session_file_declares_its_halves(
    mock_plugin: None, build: BuildSession
) -> None:
    """Build a file stack's presenter under its name and each view under name_role."""
    session = build(Plugged, PLUGIN_STACK)

    assert isinstance(session.presenters["motor"], MockMotorPresenter)
    assert isinstance(session.views["motor_view"], MockMotorView)
    assert title_of(session, "motor_detail") == "detail"


@pytest.mark.parametrize(
    ("container", "file_role", "title"),
    [
        (Declared, {}, "detail"),
        (Declared, {"detail": {"title": "file"}}, "file"),
        (DeclaredOver, {"detail": {"title": "file"}}, "class"),
    ],
    ids=["stack-class", "file", "declare"],
)
def test_a_halfs_keywords_come_from_the_class_then_the_file_then_declare(
    container: type[Session],
    file_role: dict[str, Any],
    title: str,
    mock_plugin: None,
    build: BuildSession,
) -> None:
    """Take a half's keywords from the stack class, then the file, then the session's Declare."""
    session = build(container, {**PLUGIN_STACK, "stacks": {"motor": file_role}})

    assert title_of(session, "motor_detail") == title


def test_a_stack_in_the_class_reads_its_file_entry(
    mock_plugin: None, build: BuildSession
) -> None:
    """Make one stack from an annotation and the file entry under its name."""
    config = {**PLUGIN_STACK, "stacks": {"motor": {"view": {"title": "file"}}}}
    session = build(Declared, config)

    assert list(session.presenters) == ["motor"]
    assert title_of(session, "motor_view") == "file"
    assert title_of(session, "motor_detail") == "detail"


def test_a_role_the_stack_does_not_have_is_refused() -> None:
    """Raise naming the stack and its roles for an unknown role key."""
    with pytest.raises(TypeError, match=r"'duo'.*'presenter', 'view'"):
        WithDuo({"stacks": {"duo": {"views": {}}}}).build()


@pytest.mark.parametrize(
    "bad", [NoPresenter, TwoPresenters, NoView, WithDevice, TakesArgument]
)
def test_a_stack_class_breaking_the_rules_is_refused(bad: type) -> None:
    """Refuse a stack without one presenter, without a view, holding a device, or whose constructor needs an argument."""
    holder = type("Holder", (Session,), {"__annotations__": {"stack": AsAnyStack[bad]}})

    with pytest.raises(TypeError, match=bad.__name__):
        holder().build()


def test_a_half_name_clashing_with_a_declaration_is_refused() -> None:
    """Raise naming the stack and the declaration a half name clashes with."""
    with pytest.raises(TypeError, match=r"stack 'duo'.*'duo_view'"):
        Clashing().build()


def test_a_role_entry_that_is_not_a_mapping_is_refused() -> None:
    """Refuse a file stack whose role is not a mapping of keywords."""
    with pytest.raises(ConfigurationError, match="role 'view'"):
        WithDuo({"stacks": {"duo": {"view": 3}}}).build()


def test_a_file_stack_that_does_not_resolve_is_left_out(
    mock_plugin: None, caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Log and leave out a file stack whose plugin id is unknown."""
    stacks = {"motor": {"plugin_name": "mock-bundle", "plugin_id": "nobody"}}
    with caplog.at_level(logging.ERROR, logger="redsun"):
        session = build(Plugged, {**PLUGIN_STACK, "stacks": stacks})

    assert "Failed to load stack 'motor'" in caplog.text
    assert not session.presenters
    assert not session.views


def test_stacks_of_layered_files_merge(mock_plugin: None, build: BuildSession) -> None:
    """Lay a later file's role entry over an earlier file's stack."""
    later = {"stacks": {"motor": {"detail": {"title": "later"}}}}
    session = build(Plugged, [PLUGIN_STACK, later])

    assert title_of(session, "motor_detail") == "later"
    assert "motor_view" in session.views
