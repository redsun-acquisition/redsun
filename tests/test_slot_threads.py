"""Where a slot runs: the slot says, then its class, then the frontend."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, ClassVar

import pytest
from psygnal import Signal, emit_queued

from redsun import AsPresenter, Frontend, Session, slot

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from redsun import Link
    from redsun.ports import SlotThread

    from .conftest import BuildSession


class Talker:
    sig_said = Signal(str)

    def __init__(self, name: str) -> None:
        self.name = name


class Listener:
    """Records what it hears, and the thread it heard it on."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.heard: list[tuple[str, str]] = []

    @slot
    def hear(self, text: str) -> None:
        self.heard.append((text, threading.current_thread().name))


class OnMain(Listener):
    """Every slot of the class on the main thread."""

    __redsun_slot_thread__: ClassVar[SlotThread] = "main"


class OnCurrent(OnMain):
    """One slot naming its own thread, over what its class says."""

    @slot(thread="current")
    def hear(self, text: str) -> None:
        super().hear(text)


class Awaiting:
    def __init__(self, name: str) -> None:
        self.name = name
        self.heard: list[str] = []

    @slot
    async def hear(self, text: str) -> None:
        self.heard.append(text)


class ListenersOnMain(Frontend):
    """A frontend running every listener on the main thread."""

    @classmethod
    def thread_of(cls, consumer: object) -> SlotThread:
        return "main" if isinstance(consumer, Listener) else None


class Unsaid(Session):
    talker: AsPresenter[Talker]
    listener: AsPresenter[Listener]

    def wire(self) -> Iterator[Link]:
        yield self.talker.sig_said, self.listener.hear


class SaidByTheFrontend(Unsaid):
    frontend = ListenersOnMain


class SaidByTheClass(Session):
    talker: AsPresenter[Talker]
    listener: AsPresenter[OnMain]

    def wire(self) -> Iterator[Link]:
        yield self.talker.sig_said, self.listener.hear


class SaidByTheSlot(Session):
    frontend = ListenersOnMain

    talker: AsPresenter[Talker]
    listener: AsPresenter[OnCurrent]

    def wire(self) -> Iterator[Link]:
        yield self.talker.sig_said, self.listener.hear


class AwaitingApp(Session):
    talker: AsPresenter[Talker]
    listener: AsPresenter[Awaiting]

    def wire(self) -> Iterator[Link]:
        yield self.talker.sig_said, self.listener.hear


@pytest.mark.parametrize(
    ("session", "thread"),
    [
        pytest.param(Unsaid, None, id="nothing-says"),
        pytest.param(SaidByTheFrontend, "main", id="the-frontend-says"),
        pytest.param(SaidByTheClass, "main", id="the-class-says"),
        pytest.param(SaidByTheSlot, "current", id="the-slot-says-over-both"),
    ],
)
def test_a_link_runs_where_the_nearest_declaration_says(
    session: type[Session], thread: SlotThread, build: BuildSession
) -> None:
    [link] = build(session).connections

    assert link.thread == thread


def test_a_slot_held_for_the_main_thread_waits_for_it(build: BuildSession) -> None:
    app = build(SaidByTheClass)
    emitting = threading.Thread(target=app.talker.sig_said.emit, args=("hi",))

    emitting.start()
    emitting.join()
    assert app.listener.heard == []

    emit_queued()
    assert app.listener.heard == [("hi", threading.main_thread().name)]


def test_a_session_with_no_frontend_connects_a_coroutine_slot(
    build: BuildSession, wait_until: Callable[..., bool]
) -> None:
    app = build(AwaitingApp)

    app.talker.sig_said.emit("hi")

    assert wait_until(lambda: app.listener.heard == ["hi"])
