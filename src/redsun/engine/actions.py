"""Decorators and types for continuous, interactive plans.

A *continuous* plan loops until stopped, and may be paused and resumed and take
actions the user triggers while it runs.

- `SRLatch`: an ``asyncio`` set-reset latch synchronising a plan with outside
  signals.
- `continuous`: marks a plan as continuous, recording whether it is
  pausable.
- `PlanAction`: what a plan declares of an action: its name, its description
  and the labels of its button.
- `ActionManager`: the actions a running plan offers, asked for from outside and
  reported as they change state.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, TypeVar, overload

from psygnal import Signal

from redsun.engine.plan_stubs import SIXTY_FPS, wait_for_actions
from redsun.ports import slot

if TYPE_CHECKING:
    from collections.abc import Callable

    from bluesky.utils import MsgGenerator

F = TypeVar("F", bound="Callable[..., Any]")

logger = logging.getLogger("redsun")


class SRLatch:
    """An ``asyncio`` set-reset latch, settable from any thread.

    Two `asyncio.Event` objects let a coroutine wait for either the *set* or the
    *reset* state. A new latch is reset. The first wait binds the latch to its
    loop; a `set` or `reset` from another thread is forwarded to that loop.
    """

    def __init__(self) -> None:
        self._flag: bool = False
        self._set_event: asyncio.Event = asyncio.Event()
        self._reset_event: asyncio.Event = asyncio.Event()
        self._reset_event.set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._changed_at = 0.0

    def set(self) -> None:
        """Set the latch, waking every coroutine in `wait_for_set`.

        Does nothing if already set.
        """
        if self._forwarded(self.set):
            return
        if not self._flag:
            self._flag = True
            self._changed_at = time.monotonic()
            self._set_event.set()
            self._reset_event.clear()

    def reset(self) -> None:
        """Reset the latch, waking every coroutine in `wait_for_reset`.

        Does nothing if already reset.
        """
        if self._forwarded(self.reset):
            return
        if self._flag:
            self._flag = False
            self._changed_at = time.monotonic()
            self._reset_event.set()
            self._set_event.clear()

    def _forwarded(self, call: Callable[[], None]) -> bool:
        """Hand *call* to the latch's loop when called off it, and say so."""
        if self._loop is None:
            return False
        try:
            on_loop = asyncio.get_running_loop() is self._loop
        except RuntimeError:
            on_loop = False
        if on_loop:
            return False
        self._loop.call_soon_threadsafe(call)
        return True

    def is_set(self) -> bool:
        """Return whether the latch is set."""
        return self._flag

    @property
    def changed_at(self) -> float:
        """When the latch last changed state, as `time.monotonic` reads it.

        ``0.0`` for a latch that never changed.
        """
        return self._changed_at

    async def wait_for_set(self) -> None:
        """Wait until the latch is set; return at once if it already is."""
        self._loop = asyncio.get_running_loop()
        if self._flag:
            return
        await self._set_event.wait()

    async def wait_for_reset(self) -> None:
        """Wait until the latch is reset; return at once if it already is."""
        self._loop = asyncio.get_running_loop()
        if not self._flag:
            return
        await self._reset_event.wait()


@dataclass(frozen=True)
class Continuous:
    """What `continuous` records on the plan it marks."""

    pausable: bool = False
    """Whether the run engine can pause and resume the plan."""


@overload
def continuous(func: F, /) -> F: ...


@overload
def continuous(*, pausable: bool = False) -> Callable[[F], F]: ...


def continuous(
    func: F | None = None, /, *, pausable: bool = False
) -> F | Callable[[F], F]:
    """Mark a plan as continuous: it loops until it is stopped.

    A continuous plan gets a toggle to start and stop it, and with *pausable*
    a button to pause and resume it. Usable with or without arguments:

    ```python
    @continuous
    def my_plan() -> MsgGenerator[None]: ...


    @continuous(pausable=True)
    def my_plan(detectors: Sequence[DetectorProtocol]) -> MsgGenerator[None]: ...
    ```

    The signature is untouched; what was asked is stored on the function as
    ``__continuous__``, a `Continuous`.
    """

    def decorator(plan: F) -> F:
        # setattr keeps mypy happy: Callable has no such attribute to assign
        setattr(plan, "__continuous__", Continuous(pausable=pausable))  # noqa: B010
        return plan

    return decorator if func is None else decorator(func)


@dataclass(frozen=True, kw_only=True)
class PlanAction:
    """An action a user triggers while a continuous plan runs.

    A declaration only. A plan names it as the default of a parameter, from
    which its button is made, and waits for it through an `ActionManager`.

    Subclass it to add fields; the subclass is a frozen dataclass too.
    """

    name: str
    """Name of the action."""

    description: str = ""
    """Short description of the action, usable as a tooltip."""

    toggle_states: tuple[str, str] | None = None
    """Labels of a button that stays pressed until it is released.

    The first is shown while it is released and the second while it is
    pressed. ``None`` for a button that is clicked.
    """


class ActionState(StrEnum):
    """What an action is doing, as `ActionManager.sig_changed` reports it."""

    OFFERED = "offered"
    """A plan waits for it."""

    WITHDRAWN = "withdrawn"
    """No longer waited for: the plan took another, or stopped waiting."""

    REQUESTED = "requested"
    """Asked for, and not yet taken by the plan."""

    RUNNING = "running"
    """The plan took it."""

    RELEASED = "released"
    """Asked to end while it runs."""

    DONE = "done"
    """The plan finished it."""

    REFUSED = "refused"
    """Asked for while no plan offered it, or asked to end while not running."""


class ActionManager:
    """The actions a running plan offers, and the state each is in.

    Whoever owns the plans owns one. A plan waits on it with `wait`, a user
    asks through `request`, and `sig_changed` reports every change, so the
    engine running the plan needs to know nothing of actions.
    """

    sig_changed = Signal(str, str)
    """Emitted with the name of an action and its new `ActionState`."""

    def __init__(self) -> None:
        self._offered: dict[str, SRLatch] = {}
        self._running: dict[str, SRLatch] = {}

    @slot
    def request(self, name: str, on: bool = True) -> None:
        """Ask for the action *name*, or with ``on=False`` ask a running one to end.

        Safe from any thread. Asking for an action no plan offers, or asking
        one that is not running to end, raises nothing: it is logged and
        reported as `ActionState.REFUSED`.
        """
        latch = (self._offered if on else self._running).get(name)
        if latch is None:
            logger.warning(
                "PlanAction %r refused: %s",
                name,
                "no plan offers it" if on else "it is not running",
            )
            self.sig_changed.emit(name, ActionState.REFUSED)
            return
        # reported first: the plan wakes on another thread as soon as the
        # latch changes, and would report its own state ahead of this one
        self.sig_changed.emit(
            name, ActionState.REQUESTED if on else ActionState.RELEASED
        )
        if on:
            latch.set()
        else:
            latch.reset()

    def wait(
        self, *actions: PlanAction, poll_interval: float = SIXTY_FPS
    ) -> MsgGenerator[str]:
        """Offer *actions*, wait until one is asked for, and return its name.

        Every call offers latches of its own, so a request left from an
        earlier wait cannot fire an action of this one. The action returned
        runs until `done`. The others are withdrawn, as all of them are when
        the plan is stopped while it waits. A checkpoint is yielded every
        *poll_interval* seconds, so it cannot be used between ``create`` and
        ``save``.

        Raises
        ------
        ValueError
            If no action is given.
        """
        latches = {action.name: SRLatch() for action in actions}
        for name in latches:
            self._running.pop(name, None)
        self._offered = latches
        for name in latches:
            self.sig_changed.emit(name, ActionState.OFFERED)
        taken: str | None = None
        try:
            taken, latch = yield from wait_for_actions(latches, poll_interval)
        finally:
            self._offered = {}
            for name in latches:
                if name != taken:
                    self.sig_changed.emit(name, ActionState.WITHDRAWN)
        self._running[taken] = latch
        self.sig_changed.emit(taken, ActionState.RUNNING)
        return taken

    def wait_released(
        self, action: PlanAction, poll_interval: float = SIXTY_FPS
    ) -> MsgGenerator[None]:
        """Wait until the running *action* is asked to end.

        Raises
        ------
        ValueError
            If *action* is not running.
        """
        latch = self._running.get(action.name)
        if latch is None:
            raise ValueError(f"action {action.name!r} is not running")
        yield from wait_for_actions(
            {action.name: latch}, poll_interval, wait_for="reset"
        )

    def done(self, name: str) -> None:
        """Say the plan finished the action *name*."""
        self._running.pop(name, None)
        self.sig_changed.emit(name, ActionState.DONE)


__all__ = [
    "ActionManager",
    "ActionState",
    "Continuous",
    "PlanAction",
    "SRLatch",
    "continuous",
]
