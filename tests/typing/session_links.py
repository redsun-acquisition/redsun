"""A link's slot is a function or a coroutine function, returning a value or not.

Never imported or executed; checked by the project's normal mypy invocation.
"""

from __future__ import annotations

from collections.abc import Iterator

from psygnal import Signal

from redsun import AsPresenter, Link, Session, slot


class Talker:
    sig_said = Signal(str)

    def __init__(self, name: str) -> None:
        self.name = name


class Listener:
    def __init__(self, name: str) -> None:
        self.name = name

    @slot
    def hear(self, text: str) -> None: ...

    @slot
    async def hear_later(self, text: str) -> None: ...

    @slot
    def answer(self, text: str) -> int:
        return len(text)


class App(Session):
    talker: AsPresenter[Talker]
    listener: AsPresenter[Listener]

    def wire(self) -> Iterator[Link]:
        yield self.talker.sig_said, self.listener.hear
        yield self.talker.sig_said, self.listener.hear_later
        yield self.talker.sig_said, self.listener.answer
