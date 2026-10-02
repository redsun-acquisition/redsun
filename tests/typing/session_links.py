"""A link's slot returns nothing, or is a coroutine function returning nothing.

Never imported or executed; checked by the project's normal mypy invocation.
A slot returning a value is refused, so the `type: ignore` below is needed:
mypy's `warn_unused_ignores` fails this module if `Link` ever accepts it.
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
        yield self.talker.sig_said, self.listener.answer  # type: ignore[misc]
