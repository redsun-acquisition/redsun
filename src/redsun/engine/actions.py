"""Decorators and types for continuous, interactive plans.

A *continuous* plan loops until stopped, and may be paused and resumed and take
actions the user triggers while it runs.

- `SRLatch`: an ``asyncio`` set-reset latch synchronising a plan with outside
  signals.
- `continous`: marks a plan as continuous, recording whether it is
  ``togglable`` and ``pausable``.
- `Action`: a dataclass describing one action (name, description, toggle state).
- `ContinousPlan`: a `typing.Protocol` typing decorated plans, also usable with
  ``isinstance``.
"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    ParamSpec,
    Protocol,
    TypeVar,
    cast,
    overload,
    runtime_checkable,
)

if TYPE_CHECKING:
    from collections.abc import Callable

P = ParamSpec("P")
R = TypeVar("R")
R_co = TypeVar("R_co", covariant=True)


class SRLatch:
    """An ``asyncio`` set-reset latch.

    Two `asyncio.Event` objects let a coroutine wait for either the *set* or the
    *reset* state. A new latch is reset.
    """

    def __init__(self) -> None:
        self._flag: bool = False
        self._set_event: asyncio.Event = asyncio.Event()
        self._reset_event: asyncio.Event = asyncio.Event()
        self._reset_event.set()

    def set(self) -> None:
        """Set the latch, waking every coroutine in `wait_for_set`.

        Does nothing if already set.
        """
        if not self._flag:
            self._flag = True
            self._set_event.set()
            self._reset_event.clear()

    def reset(self) -> None:
        """Reset the latch, waking every coroutine in `wait_for_reset`.

        Does nothing if already reset.
        """
        if self._flag:
            self._flag = False
            self._reset_event.set()
            self._set_event.clear()

    def is_set(self) -> bool:
        """Return whether the latch is set."""
        return self._flag

    async def wait_for_set(self) -> None:
        """Wait until the latch is set; return at once if it already is."""
        if self._flag:
            return
        await self._set_event.wait()

    async def wait_for_reset(self) -> None:
        """Wait until the latch is reset; return at once if it already is."""
        if not self._flag:
            return
        await self._reset_event.wait()


@overload
def continous(
    func: Callable[P, R_co],
    /,
) -> ContinousPlan[P, R_co]: ...


@overload
def continous(
    *,
    togglable: bool = True,
    pausable: bool = False,
) -> Callable[[Callable[P, R_co]], ContinousPlan[P, R_co]]: ...


def continous(
    func: Callable[P, R_co] | None = None,
    /,
    *,
    togglable: bool = True,
    pausable: bool = False,
) -> Callable[[Callable[P, R_co]], ContinousPlan[P, R_co]] | ContinousPlan[P, R_co]:
    """Mark a plan as continuous.

    A continuous plan gets UI controls to start, stop, pause and resume it.
    Usable with or without arguments:

    ```python
    @continous
    def my_plan() -> MsgGenerator[None]: ...


    @continous(togglable=True, pausable=True)
    def my_plan(detectors: Sequence[DetectorProtocol]) -> MsgGenerator[None]: ...
    ```

    Parameters
    ----------
    togglable : bool, optional
        Whether the plan loops until stopped with a toggle button.
    pausable : bool, optional
        Whether the run engine can pause and resume the plan.

    Returns
    -------
    ContinousPlan
        The decorated plan function, typed as a `ContinousPlan`.

    Notes
    -----
    The signature is untouched; the flags are stored on the function as
    ``__togglable__`` and ``__pausable__``.
    """

    def decorator(func: Callable[P, R_co]) -> ContinousPlan[P, R_co]:
        # setattr keeps mypy happy: Callable has no such attributes to assign
        setattr(func, "__togglable__", togglable)  # noqa: B010
        setattr(func, "__pausable__", pausable)  # noqa: B010
        return cast("ContinousPlan[P, R_co]", func)

    if func is None:
        return decorator

    return decorator(func)


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


@runtime_checkable
class ContinousPlan(Protocol[P, R_co]):
    """Protocol for plans decorated with `continous`.

    The return type of `continous`, also usable with ``isinstance``:

    ```python
    if isinstance(f, ContinousPlan):
        print(f.__togglable__, f.__pausable__)
    ```

    Attributes
    ----------
    __togglable__ : bool
        Whether the plan loops until the run engine stops it.
    __pausable__ : bool
        Whether the run engine can pause and resume the plan.
    """

    __togglable__: bool
    __pausable__: bool

    @abstractmethod
    def __call__(  # noqa: D102
        self, *args: P.args, **kwargs: P.kwargs
    ) -> R_co:  # pragma: no cover - protocol
        ...


__all__ = [
    "Action",
    "ContinousPlan",
    "SRLatch",
    "continous",
]
