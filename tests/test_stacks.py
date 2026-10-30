"""Tests for declaring a presenter and its views as one stack."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Annotated, Any

import pytest
from mock_bundle.devices import MockStage
from mock_bundle.presenters import MockMotorPresenter
from mock_bundle.stacks import MockMotorStack
from mock_bundle.views import MockMotorView, Somewhere
from psygnal import Signal

from redsun import (
    Alias,
    AsDevice,
    AsPresenter,
    AsStack,
    AsView,
    BuildError,
    ConfigurationError,
    Declare,
    Link,
    Placement,
    Session,
    WiringError,
    slot,
)
from redsun.qt import QtSession

if TYPE_CHECKING:
    from qtpy import QtWidgets

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

    @slot(signal="sig_said")
    def hear(self, text: str) -> None:
        self.heard = text


class Deaf:
    """A view with no slot a talker's signal reaches."""

    placement: Placement = Somewhere()

    def __init__(self, name: str) -> None:
        self.name = name


class Duo:
    """A talker with its hearer."""

    presenter: AsPresenter[Talker]
    view: AsView[Hearer]


class BrokenTalker(Talker):
    """A talker whose constructor raises, so the build skips it."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        raise RuntimeError("this presenter cannot be made")


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


class Unheard:
    presenter: AsPresenter[Talker]
    view: AsView[Deaf]


class BrokenDuo:
    presenter: AsPresenter[BrokenTalker]
    view: AsView[Hearer]


class Marked:
    presenter: AsPresenter[Talker]
    view: Annotated[AsView[Hearer], Alias("other")]


class Reserved:
    presenter: AsPresenter[Talker]
    plugin_id: AsView[Hearer]


class Unconstructable:
    presenter: AsPresenter[Talker]
    view: AsView[Hearer]

    def __init__(self) -> None:
        raise RuntimeError("this stack cannot be made")


class Plugged(Session):
    """Every component comes from the mock bundle."""


class WithDuo(Session):
    duo: AsStack[Duo]


class WithUnheard(Session):
    duo: AsStack[Unheard]


class WithBrokenDuo(Session):
    duo: AsStack[BrokenDuo]

    def wire(self) -> Iterator[Link]:
        yield self.duo.presenter.sig_said, self.duo.view.hear


class WithAliasedDuo(Session):
    panel: Annotated[AsStack[Duo], Alias("duo")]


class WithUnknownRole(Session):
    duo: Annotated[AsStack[Duo], Declare(views={})]


class WithScalarRole(Session):
    duo: Annotated[AsStack[Duo], Declare(view=3)]


class WithMarked(Session):
    duo: AsStack[Marked]


class WithReserved(Session):
    duo: AsStack[Reserved]


class WithUnconstructable(Session):
    broken: AsPresenter[BrokenTalker]
    duo: AsStack[Unconstructable]


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


def test_a_role_that_names_a_plugin_key_is_refused() -> None:
    """Raise naming the stack class and the role for a role called plugin_id."""
    with pytest.raises(TypeError, match=r"Reserved.*'plugin_id'"):
        WithReserved().build()


def test_a_half_with_a_marker_other_than_declare_is_refused() -> None:
    """Raise naming the stack class and the role for an Alias on a half."""
    with pytest.raises(TypeError, match=r"Marked.*'view'.*Alias"):
        WithMarked().build()


def test_a_declare_role_that_is_not_a_mapping_is_refused() -> None:
    """Raise naming the stack and the role for a Declare giving a scalar."""
    with pytest.raises(TypeError, match=r"role 'view' of stack 'duo'"):
        WithScalarRole().build()


def test_a_declare_naming_a_role_the_stack_does_not_have_is_refused() -> None:
    """Raise naming the stack and its roles for a Declare with an unknown role."""
    with pytest.raises(TypeError, match=r"'duo' has no role 'views'.*'presenter'"):
        WithUnknownRole().build()


def test_a_stack_declared_under_alias_is_held_by_its_attribute(
    build: BuildSession,
) -> None:
    """Hold the stack under the annotated attribute and build its halves under the alias."""
    session = build(WithAliasedDuo)

    assert isinstance(session.panel, Duo)
    assert session.panel.presenter is session.presenters["duo"]
    assert session.panel.view is session.views["duo_view"]


def test_a_stack_that_cannot_be_made_leaves_no_stand_ins() -> None:
    """Remove the stand-ins of failed components when a stack's constructor raises."""
    session = WithUnconstructable()

    with pytest.raises(RuntimeError, match="this stack cannot be made"):
        session.build()

    assert not hasattr(session, "broken")


UNRESOLVED_STACK: dict[str, Any] = {
    "plugin_name": "mock-bundle",
    "plugin_id": "nobody",
    "view": {},
}


def test_a_file_stack_that_does_not_resolve_fails_the_build_of_a_strict_session(
    mock_plugin: None,
) -> None:
    """Raise BuildError naming a file stack whose plugin id is unknown."""
    config = {**PLUGIN_STACK, "stacks": {"motor": UNRESOLVED_STACK}, "strict": True}

    with pytest.raises(BuildError, match="motor"):
        Plugged(config).build()


def test_links_naming_the_halves_of_an_unresolved_stack_are_skipped(
    mock_plugin: None, caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Build without an unresolved stack and warn about the pair that names its halves."""
    config = {
        **PLUGIN_STACK,
        "stacks": {"motor": UNRESOLVED_STACK},
        "pairs": [["motor", "motor_view"]],
    }
    with caplog.at_level(logging.WARNING, logger="redsun"):
        session = build(Plugged, config)

    assert session.is_built
    assert not session.presenters
    assert "Not pairing" in caplog.text


def test_a_later_file_replaces_a_stack_entry_whole(
    mock_plugin: None, build: BuildSession
) -> None:
    """Drop the keywords an earlier file gave a role when a later file lists the stack."""
    plugin = {"plugin_name": "mock-bundle", "plugin_id": "mock-motor"}
    earlier = {
        **PLUGIN_STACK,
        "stacks": {"motor": {**plugin, "view": {"title": "earlier"}}},
    }
    later = {"stacks": {"motor": {**plugin, "detail": {"title": "later"}}}}
    session = build(Plugged, [earlier, later])

    assert title_of(session, "motor_view") == ""
    assert title_of(session, "motor_detail") == "later"


def test_a_stack_pairs_its_presenter_with_each_view(
    mock_plugin: None, build: BuildSession
) -> None:
    """Link a file stack's presenter to both of its views."""
    session = build(Plugged, PLUGIN_STACK)

    assert sorted(
        (c.publisher, c.publisher_port, c.consumer, c.consumer_port)
        for c in session.connections
    ) == [
        ("motor", "sig_moved", "motor_detail", "refresh"),
        ("motor", "sig_moved", "motor_view", "refresh"),
    ]


def test_the_session_holds_the_stack_with_its_built_halves(
    build: BuildSession,
) -> None:
    """Hold an instance of the stack class whose roles are the built halves."""
    session = build(WithDuo)

    assert isinstance(session.duo, Duo)
    assert session.duo.presenter is session.presenters["duo"]
    assert session.duo.view is session.views["duo_view"]


def test_a_stack_also_listed_under_pairs_links_each_once(
    build: BuildSession,
) -> None:
    """Make each link once when the file also pairs a stack's halves."""
    session = build(WithDuo, {"pairs": [["duo", "duo_view"]]})

    session.duo.presenter.sig_said.emit("hi")

    assert len(session.connections) == 1
    assert session.duo.view.heard == "hi"


def test_a_stack_whose_view_links_nothing_is_refused() -> None:
    """Raise when a stack's view shares no link with its presenter."""
    with pytest.raises(WiringError, match="'duo_view' with 'duo' connects nothing"):
        WithUnheard().build()


def test_a_stack_half_that_failed_is_skipped_and_stands_in_during_wire(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Build without a failed half, warn about its pairing, and stand it in during wire."""
    with caplog.at_level(logging.WARNING, logger="redsun"):
        session = build(WithBrokenDuo)

    assert session.is_built
    assert "Not pairing duo_view with duo" in caplog.text
    assert "Not connecting duo.sig_said" in caplog.text
    assert not hasattr(session.duo, "presenter")
    assert session.duo.view is session.views["duo_view"]


@pytest.mark.qt
@pytest.mark.parametrize("stack", ["acquisition", "lights", "positioner"])
def test_a_built_in_stack_makes_the_links_of_its_pair(
    qapp: QtWidgets.QApplication, build: BuildSession, stack: str
) -> None:
    """Link a built-in stack exactly as its presenter and view paired by hand."""

    def entry(plugin_id: str) -> dict[str, str]:
        return {"plugin_name": "redsun", "plugin_id": plugin_id}

    def links(session: Session) -> list[tuple[str, str, str, str]]:
        return sorted(
            (c.publisher, c.publisher_port, c.consumer, c.consumer_port)
            for c in session.connections
        )

    by_hand = build(
        QtSession.from_config(
            {
                "session": f"hand-{stack}",
                "mock": True,
                "presenters": {stack: entry(stack)},
                "views": {f"{stack}_view": entry(stack)},
                "pairs": [[f"{stack}_view", stack]],
            }
        )
    )
    expected = links(by_hand)
    by_hand.shutdown()
    declared = build(
        QtSession.from_config(
            {
                "session": f"stack-{stack}",
                "mock": True,
                "stacks": {stack: entry(stack)},
            }
        )
    )

    assert expected
    assert links(declared) == expected
