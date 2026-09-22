from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING, Any

import bluesky.plan_stubs as bps
import dependency_injector.providers as dip
from bluesky.suspenders import SuspendBoolHigh

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from bluesky.utils import MsgGenerator

    from ._wrapper import RunEngine

__all__ = ["DEFERRALS", "Deferrals"]

logger = logging.getLogger("redsun")


class Flag:
    """A boolean a suspender can watch.

    What a suspender needs of an ``ophyd`` signal and nothing more: a name,
    ``subscribe``, ``clear_sub``, and a call to each watcher with the value
    when it changes.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._value = False
        self._watchers: list[Callable[..., None]] = []

    def subscribe(
        self, watcher: Callable[..., None], *, event_type: Any = None, run: bool = True
    ) -> None:
        """Call *watcher* with every value set from now on, and now if *run*."""
        self._watchers.append(watcher)
        if run:
            watcher(self._value)

    def clear_sub(self, watcher: Callable[..., None]) -> None:
        """Stop calling *watcher*."""
        self._watchers.remove(watcher)

    def set(self, value: bool) -> None:
        """Set the value and tell every watcher."""
        self._value = value
        for watcher in list(self._watchers):
            watcher(value)


class Deferrals:
    """Changes to apply the next time the engine is between two messages.

    A change asked for while a plan runs waits: the engine suspends the plan
    once the message under way completes, applies every change queued by
    then on its own loop, and resumes. One asked for while no plan runs is
    applied on that loop at once: before `request` returns when called from
    a thread without an event loop, without waiting otherwise, since waiting
    on a loop would block it. A change that raises is logged, and the ones
    after it still run.
    """

    def __init__(self, engine: RunEngine) -> None:
        self._engine = engine
        self._queue: deque[Callable[[], Awaitable[None]]] = deque()
        self._pending = Flag("deferrals")
        self._engine.install_suspender(
            SuspendBoolHigh(self._pending, pre_plan=self._drain)
        )

    def request(self, apply: Callable[[], Awaitable[None]]) -> None:
        """Queue *apply*, or run it now when no plan is running."""
        if self._engine.state != "running":
            applied = asyncio.run_coroutine_threadsafe(
                self._apply(apply), self._engine.loop
            )
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                applied.result()
            return
        self._queue.append(apply)
        # raised on the engine's loop: tripped from another thread, the
        # suspender waits 0.1 s for that loop to make its event, and raises
        # when a busy machine takes longer
        self._engine.loop.call_soon_threadsafe(self._pending.set, True)

    def _drain(self) -> MsgGenerator[None]:
        """Apply every queued change on the engine's loop, then let the plan resume."""
        yield from bps.wait_for([self._apply_queued])
        self._pending.set(False)
        # a change queued between the last one applied and the resume would
        # otherwise wait for the next request to raise the flag again
        if self._queue:
            self._pending.set(True)

    async def _apply_queued(self) -> None:
        while self._queue:
            await self._apply(self._queue.popleft())

    async def _apply(self, apply: Callable[[], Awaitable[None]]) -> None:
        try:
            await apply()
        except Exception:
            logger.exception("A deferred change failed")


DEFERRALS: dip.Dependency[Deferrals] = dip.Dependency(instance_of=Deferrals)
"""Key under which the engine's owner provides its `Deferrals`."""
