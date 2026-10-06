"""Tests for pairing two components in a session."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, ClassVar

from psygnal import Signal

from redsun import AsPresenter, Link, Session, slot

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


def test_a_link_yielded_twice_is_made_once(build: BuildSession) -> None:
    """Connect a link `wire` yields twice only once."""
    session = build(SaidTwice)

    session.talker.sig_said.emit("hi")

    assert session.listener.heard == ["hi"]
    assert len(session.connections) == 1
