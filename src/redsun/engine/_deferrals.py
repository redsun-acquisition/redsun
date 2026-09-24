from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING, Any

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from concurrent.futures import Future

    from bluesky.utils import Msg, MsgGenerator

    from ._wrapper import RunEngine

__all__ = ["Deferrals"]

logger = logging.getLogger("redsun")


class Deferrals:
    """Changes to apply before the next message of the running plan.

    Every change runs on the engine's loop. One asked for while a plan runs
    waits for the message under way to complete, then runs before the next
    message is sent, or before the plan returns if that message was its
    last; the plan is neither suspended nor rewound. One asked for while no
    plan runs is applied at once. A change that raises is logged, and the
    ones after it still run.
    """

    def __init__(self, engine: RunEngine) -> None:
        self._engine = engine
        self._queue: deque[
            tuple[Callable[[], Awaitable[None]], asyncio.Future[None]]
        ] = deque()
        # the mutator sees the messages it inserts too, so the drain it
        # inserts must not be wrapped in another drain
        self._draining = False
        self._engine.preprocessors.append(self.wrap)
        # a halted plan skips its cleanup, so the changes it leaves wait for idle
        self._engine.sig_state_changed.connect(self._on_state)

    def request(self, apply: Callable[[], Awaitable[None]]) -> Future[None]:
        """Ask for *apply* to run, and return a future done once it did.

        Safe from any thread. A caller on a loop must not block on the future.
        """
        return asyncio.run_coroutine_threadsafe(
            self._schedule(apply), self._engine.loop
        )

    def wrap(self, plan: MsgGenerator[Any]) -> MsgGenerator[Any]:
        """Run the changes queued so far before each message of *plan* and before it returns."""

        def before(msg: Msg) -> tuple[MsgGenerator[Any] | None, None]:
            if self._draining or not self._queue:
                return None, None

            def head() -> MsgGenerator[Any]:
                self._draining = True
                try:
                    yield from bps.wait_for([self._apply_queued])
                finally:
                    self._draining = False
                return (yield msg)

            return head(), None

        def leftovers() -> MsgGenerator[None]:
            # asked for during the last message, which no message follows
            if self._queue:
                yield from bps.wait_for([self._apply_queued])

        wrapped: MsgGenerator[Any] = bpp.finalize_wrapper(
            bpp.plan_mutator(plan, before), leftovers()
        )
        return wrapped

    async def _schedule(self, apply: Callable[[], Awaitable[None]]) -> None:
        """Apply now, or queue for the next message; done once applied either way."""
        if self._engine.state != "running":
            await self._apply(apply)
            return
        done = asyncio.get_running_loop().create_future()
        self._queue.append((apply, done))
        await done

    def _on_state(self, new: str, old: str) -> None:
        if new == "idle" and self._queue:
            asyncio.run_coroutine_threadsafe(self._apply_queued(), self._engine.loop)

    async def _apply_queued(self) -> None:
        while self._queue:
            apply, done = self._queue.popleft()
            await self._apply(apply)
            done.set_result(None)

    async def _apply(self, apply: Callable[[], Awaitable[None]]) -> None:
        try:
            await apply()
        except Exception:
            logger.exception("A deferred change failed")
