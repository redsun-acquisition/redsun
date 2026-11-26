"""`remote` keeps a function's type, and async slots may return values.

Never imported or executed; checked by the project's normal mypy invocation.
"""

from __future__ import annotations

from typing import assert_type

from psygnal import Signal

from redsun import Link, remote


@remote
async def f(x: int) -> str:
    return str(x)


async def check() -> None:
    assert_type(await f(1), str)


class Emitter:
    sig = Signal(int)


class Receiver:
    async def take(self, n: int) -> int:
        return n


link: Link = (Emitter().sig, Receiver().take)
