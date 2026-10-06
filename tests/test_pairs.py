"""Tests for pairing two components in a session."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from mock_bundle.devices import MockStage
from mock_bundle.presenters import MockMotorPresenter
from mock_bundle.views import MockMotorView
from psygnal import Signal

from redsun import (
    AsDevice,
    AsPresenter,
    ConfigurationError,
    Link,
    Session,
    WiringError,
    slot,
)

if TYPE_CHECKING:
    from redsun.testing import BuildSession


class Talker:
    """A presenter announcing what it says, and hearing replies."""

    sig_said = Signal(str)

    def __init__(self, name: str) -> None:
        self.name = name
        self.replies: list[str] = []

    @slot(signal="sig_replied")
    def hear_reply(self, text: str) -> None:
        self.replies.append(text)


class Listener:
    """A presenter hearing what a talker says, and replying."""

    sig_replied = Signal(str)

    def __init__(self, name: str) -> None:
        self.name = name
        self.heard: list[str] = []

    @slot(signal="sig_said")
    def hear(self, text: str) -> None:
        self.heard.append(text)


class Chat(Session):
    config: ClassVar[dict[str, Any]] = {"session": "pairs-chat"}

    talker: AsPresenter[Talker]
    listener: AsPresenter[Listener]


class SaidTwice(Chat):
    def wire(self) -> Iterator[Link]:
        yield self.talker.sig_said, self.listener.hear
        yield self.talker.sig_said, self.listener.hear


class SaidAlsoConfigured(Chat):
    config: ClassVar[dict[str, Any]] = {
        "session": "pairs-chat",
        "wiring": {"talker.sig_said": "listener.hear"},
    }

    def wire(self) -> Iterator[Link]:
        yield self.talker.sig_said, self.listener.hear


class Paired(Chat):
    config: ClassVar[dict[str, Any]] = {
        "session": "pairs-chat",
        "pairs": [["talker", "listener"]],
    }


class Mute:
    """A presenter with no ports a pairing could match."""

    def __init__(self, name: str) -> None:
        self.name = name


class Broken(Talker):
    """A talker whose constructor raises, so the build skips it."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        raise RuntimeError("this presenter cannot be made")


class Demanding:
    """A presenter whose slot needs more than a talker sends."""

    def __init__(self, name: str) -> None:
        self.name = name

    @slot(signal="sig_said")
    def hear_twice(self, text: str, again: str) -> None: ...


class Trio(Chat):
    other: AsPresenter[Listener]


class Wired(Trio):
    def wire(self) -> Iterator[Link]:
        yield self.talker.sig_said, self.other.hear


class AlreadyWired(Chat):
    def wire(self) -> Iterator[Link]:
        yield self.talker.sig_said, self.listener.hear
        yield self.listener.sig_replied, self.talker.hear_reply


class Silent(Session):
    config: ClassVar[dict[str, Any]] = {"session": "pairs-silent"}

    talker: AsPresenter[Talker]
    mute: AsPresenter[Mute]


class HalfBuilt(Session):
    config: ClassVar[dict[str, Any]] = {"session": "pairs-half"}

    broken: AsPresenter[Broken]
    listener: AsPresenter[Listener]


class Mismatched(Session):
    config: ClassVar[dict[str, Any]] = {"session": "pairs-mismatched"}

    talker: AsPresenter[Talker]
    demanding: AsPresenter[Demanding]


class WithStage(Session):
    config: ClassVar[dict[str, Any]] = {"session": "pairs-stage"}

    stage: AsDevice[MockStage]
    listener: AsPresenter[Listener]


class Plugged(Session):
    """Every component comes from the mock bundle."""


PLUGIN_SESSION = {
    "session": "pairs-plugin",
    "providers": {
        "services": {"plugin_name": "mock-bundle", "plugin_id": "mock-services"}
    },
    "devices": {"stage": {"plugin_name": "mock-bundle", "plugin_id": "mock-stage"}},
    "presenters": {
        "motor_ctrl": {"plugin_name": "mock-bundle", "plugin_id": "mock-motor"}
    },
    "views": {
        "motor_widget": {"plugin_name": "mock-bundle", "plugin_id": "mock-motor-view"}
    },
    "pairs": [["motor_widget", "motor_ctrl"]],
}


def test_a_link_yielded_twice_is_made_once(build: BuildSession) -> None:
    """Connect a link `wire` yields twice only once."""
    session = build(SaidTwice)

    session.talker.sig_said.emit("hi")

    assert session.listener.heard == ["hi"]
    assert len(session.connections) == 1


def test_a_link_in_wire_and_in_wiring_is_made_once(build: BuildSession) -> None:
    """Connect a link both `wire` and the `wiring` section name only once."""
    session = build(SaidAlsoConfigured)

    session.talker.sig_said.emit("hi")

    assert session.listener.heard == ["hi"]
    assert len(session.connections) == 1


def test_a_pairing_in_a_session_file_links_a_plugins_components(
    mock_plugin: None, build: BuildSession
) -> None:
    """Link a plugin's presenter to its view through the `pairs` section."""
    session = build(Plugged, PLUGIN_SESSION)
    presenter = session.presenters["motor_ctrl"]
    widget = session.views["motor_widget"]
    assert isinstance(presenter, MockMotorPresenter)
    assert isinstance(widget, MockMotorView)

    presenter.sig_moved.emit("x", 2.0)

    assert widget.refreshed == ("x", 2.0)
    assert [
        (c.publisher, c.publisher_port, c.consumer, c.consumer_port)
        for c in session.connections
    ] == [("motor_ctrl", "sig_moved", "motor_widget", "refresh")]


def test_a_pairing_links_both_ways(build: BuildSession) -> None:
    """Deliver a signal of each component of a pair to the other."""
    session = build(Chat, {"pairs": [["talker", "listener"]]})

    session.talker.sig_said.emit("hi")
    session.listener.sig_replied.emit("hello")

    assert session.listener.heard == ["hi"]
    assert session.talker.replies == ["hello"]


def test_links_come_from_wire_then_the_wiring_section_then_pairs(
    build: BuildSession,
) -> None:
    """Make the links of `wire` first, those of `wiring` next, a pairing's last."""
    session = build(
        Wired,
        {
            "wiring": {"listener.sig_replied": "talker.hear_reply"},
            "pairs": [["talker", "listener"]],
        },
    )

    assert [c.consumer for c in session.connections] == ["other", "talker", "listener"]


@pytest.mark.parametrize(
    ("container", "config"),
    [
        (AlreadyWired, {"pairs": [["talker", "listener"]]}),
        (
            Chat,
            {
                "wiring": {
                    "talker.sig_said": "listener.hear",
                    "listener.sig_replied": "talker.hear_reply",
                },
                "pairs": [["listener", "talker"]],
            },
        ),
    ],
    ids=["after-wire", "after-the-wiring-section"],
)
def test_a_pairing_over_links_already_made_makes_each_once(
    container: type[Chat], config: dict[str, Any], build: BuildSession
) -> None:
    """Make each link once, and accept a pairing whose every link was made already."""
    session = build(container, config)

    session.talker.sig_said.emit("hi")

    assert session.listener.heard == ["hi"]
    assert len(session.connections) == 2


@pytest.mark.parametrize(
    "later",
    [
        {"pairs": [["talker", "other"]]},
        {"pairs": (("talker", "other"),)},
        {"pairs": None},
        {},
    ],
    ids=["a-pairing", "a-tuple-of-pairs", "nothing-under-pairs", "no-pairs"],
)
def test_the_pairs_of_layered_sources_all_apply(
    later: dict[str, Any], build: BuildSession
) -> None:
    """Keep the pairings of earlier sources and add those of a later one."""
    session = build(Trio, [{"pairs": (("talker", "listener"),)}, later])

    session.talker.sig_said.emit("hi")

    assert session.listener.heard == ["hi"]
    assert session.other.heard == (["hi"] if later.get("pairs") else [])


def test_an_empty_pairs_section_pairs_nothing(build: BuildSession) -> None:
    """Read `pairs:` with nothing under it as no pairing."""
    build(Chat, {"pairs": None})


def test_a_pair_from_the_class_is_written_once_however_often_saved(
    build: BuildSession,
) -> None:
    """Serialize a class-level pair once, and again after each rebuild."""
    session = build(Paired)
    written = session.serialize()
    session.shutdown()
    again = build(Paired, written)
    rewritten = again.serialize()
    again.shutdown()

    assert written["pairs"] == [["talker", "listener"]]
    assert rewritten["pairs"] == written["pairs"]
    assert build(Paired, rewritten).serialize()["pairs"] == written["pairs"]


def test_a_pairing_that_connects_nothing_is_refused() -> None:
    """Raise naming both components when no slot names a signal of the other."""
    with pytest.raises(WiringError, match="'talker' with 'mute' connects nothing"):
        Silent({"pairs": [["talker", "mute"]]}).build()


def test_a_pairing_naming_a_component_that_failed_is_skipped(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Warn about and skip a pairing whose component did not build."""
    with caplog.at_level(logging.WARNING, logger="redsun"):
        session = build(HalfBuilt, {"pairs": [["broken", "listener"]]})

    assert session.is_built
    assert "Not pairing broken with listener" in caplog.text


@pytest.mark.parametrize(
    ("container", "pair", "named"),
    [
        (Chat, ["talker", "nobody"], "nobody"),
        (HalfBuilt, ["broken", "nobody"], "nobody"),
        (WithStage, ["stage", "listener"], "stage"),
    ],
    ids=["never-declared", "declared-failed-and-never-declared", "a-device"],
)
def test_a_pairing_naming_no_built_presenter_or_view_is_refused(
    container: type[Session], pair: list[str], named: str
) -> None:
    """Raise for a pairing naming an undeclared component or a device."""
    with pytest.raises(WiringError, match=f"'{named}', which is not a built presenter"):
        container({"pairs": [pair]}).build()


def test_a_pairing_naming_one_component_twice_is_refused_when_read() -> None:
    """Refuse a pairing of a component with itself before anything is built."""
    with pytest.raises(ConfigurationError, match="pairs 'talker' with itself"):
        Chat({"pairs": [["talker", "talker"]]}).build()


def test_a_pairing_whose_slot_needs_more_than_the_signal_sends_is_refused() -> None:
    """Raise when a matched slot needs more arguments than its signal sends."""
    with pytest.raises(WiringError, match="cannot connect"):
        Mismatched({"pairs": [["talker", "demanding"]]}).build()
