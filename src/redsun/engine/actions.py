"""Decorators and types for continuous, interactive plans.

A *continuous* plan loops until stopped, and may be paused and resumed and take
actions the user triggers while it runs.

- `SRLatch`: an ``asyncio`` set-reset latch synchronising a plan with outside
  signals.
- `continuous`: marks a plan as continuous, recording whether it is
  pausable.
- `Action`: a dataclass describing one action (name, description, toggle state).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import Callable

F = TypeVar("F", bound="Callable[..., Any]")


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


@dataclass(kw_only=True)
class Action:
    """Metadata for an in-flight action on a continuous plan.

    An `Action` is something the user triggers while a continuous plan runs. It
    holds an `SRLatch`, so the plan can ``await`` the trigger.

    !!! warning
        The latch is created on first access of `event_map`, so an `Action` can
        be constructed without a running event loop. Access the latch only from
        inside a plan.

    Subclass it to add fields.
    """

    name: str
    """Name of the action."""

    description: str = field(default="")
    """Short description of the action, usable as a tooltip."""

    togglable: bool = field(default=False)
    """Whether the action is togglable."""

    toggle_states: tuple[str, str] = field(default=("On", "Off"))
    """Labels of the toggle states (on, off), used when `togglable` is True."""

    _latch: SRLatch | None = field(init=False, default=None, repr=False)

    @property
    def event_map(self) -> dict[str, SRLatch]:
        """Return ``{name: latch}`` for this action."""
        if not self._latch:
            self._latch = SRLatch()
        return {self.name: self._latch}


__all__ = [
    "Action",
    "Continuous",
    "SRLatch",
    "continuous",
]
