"""Engine actions: decorators and types for continuous, interactive plans.

A *continuous* plan is one that runs in an infinite loop until explicitly stopped,
and may support pause/resume and in-flight actions (user-triggered side effects
while the plan is running).

This module provides:

- `SRLatch` — an asyncio set-reset latch used to synchronise plan execution with
  external signals.
- `continous` — a decorator that marks a plan function as continuous and records
  its ``togglable`` and ``pausable`` capabilities.
- `Action` — a dataclass carrying metadata (name, description, toggle state) for
  a single in-flight action.
- `ContinousPlan` — a `typing.Protocol` used for static typing and runtime
  ``isinstance`` checks on decorated plans.
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
    """An asyncio Event-like object that behaves as a set-reset latch.

    Wraps two `asyncio.Event` objects to allow waiting for either the *set*
    or the *reset* state of the latch.  At construction the latch starts in
    the **reset** state.
    """

    def __init__(self) -> None:
        self._flag: bool = False
        self._set_event: asyncio.Event = asyncio.Event()
        self._reset_event: asyncio.Event = asyncio.Event()
        self._reset_event.set()

    def set(self) -> None:
        """Set the internal flag to True.

        All coroutines waiting in `wait_for_set` are awakened.
        No-op if the flag is already set.
        """
        if not self._flag:
            self._flag = True
            self._set_event.set()
            self._reset_event.clear()

    def reset(self) -> None:
        """Reset the internal flag to False.

        All coroutines waiting in `wait_for_reset` are awakened.
        No-op if the flag is already reset.
        """
        if self._flag:
            self._flag = False
            self._reset_event.set()
            self._set_event.clear()

    def is_set(self) -> bool:
        """Return True if the internal flag is set, False otherwise."""
        return self._flag

    async def wait_for_set(self) -> None:
        """Wait until the internal flag is set.

        Returns immediately if the flag is already set; otherwise blocks
        until another coroutine calls `set`.
        """
        if self._flag:
            return
        await self._set_event.wait()

    async def wait_for_reset(self) -> None:
        """Wait until the internal flag is reset.

        Returns immediately if the flag is already reset; otherwise blocks
        until another coroutine calls `reset`.
        """
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

    A *continuous* plan informs the view to provide UI controls that allow
    the user to start, stop, pause, and resume plan execution.

    Can be used with or without arguments:

    ```python
    @continous
    def my_plan() -> MsgGenerator[None]: ...


    @continous(togglable=True, pausable=True)
    def my_plan(detectors: Sequence[DetectorProtocol]) -> MsgGenerator[None]: ...
    ```

    Parameters
    ----------
    togglable : bool, optional
        Whether the plan runs as an infinite loop that the run engine can
        stop via a toggle button. Default is True.
    pausable : bool, optional
        Whether the plan can be paused and resumed by the run engine.
        Default is False.

    Returns
    -------
    ContinousPlan
        The decorated plan function, typed as a `ContinousPlan`.

    Notes
    -----
    The decorator does not modify the function signature. It stores
    ``togglable`` and ``pausable`` as attributes on the function object
    (``__togglable__`` and ``__pausable__``), to be retrieved later by
    `create_plan_spec`.
    """

    def decorator(func: Callable[P, R_co]) -> ContinousPlan[P, R_co]:
        setattr(func, "__togglable__", togglable)
        setattr(func, "__pausable__", pausable)
        return cast("ContinousPlan[P, R_co]", func)

    if func is None:
        return decorator

    return decorator(func)


@dataclass(kw_only=True)
class Action:
    """Metadata for an in-flight action on a continuous plan.

    An `Action` is a user-triggerable side effect that can be fired while a
    continuous plan is running.  It encapsulates an `SRLatch` synchronisation
    primitive so the plan can ``await`` the action being triggered.

    !!! warning
        The internal `SRLatch` is created lazily on first access of
        `event_map`, so `Action` objects can be constructed without a running
        event loop.  The latch must only be accessed from within a plan.

    Subclass freely to add domain-specific fields.

    Attributes
    ----------
    name : str
        The name of the action.
    description : str
        A brief description shown as a tooltip in the UI.
        Defaults to an empty string.
    togglable : bool
        Whether the action is represented as a toggle button in the UI.
        Default is False (one-shot).
    toggle_states : tuple[str, str]
        Labels for the two toggle states (on, off).
        Only used when ``togglable`` is True.
        Default is ``("On", "Off")``.
    """

    name: str
    description: str = field(default="")
    togglable: bool = field(default=False)
    toggle_states: tuple[str, str] = field(default=("On", "Off"))
    _latch: SRLatch | None = field(init=False, default=None, repr=False)

    @property
    def event_map(self) -> dict[str, SRLatch]:
        """Return the latch for this action as a single-entry dict keyed by name."""
        if not self._latch:
            self._latch = SRLatch()
        return {self.name: self._latch}


@runtime_checkable
class ContinousPlan(Protocol[P, R_co]):
    """Protocol for plans decorated with `continous`.

    Used both for static typing (as the return type of the `continous`
    decorator) and for runtime ``isinstance`` checks:

    ```python
    if isinstance(f, ContinousPlan):
        print(f.__togglable__, f.__pausable__)
    ```

    Attributes
    ----------
    __togglable__ : bool
        Whether the plan is togglable (i.e. runs as an infinite loop that
        the run engine can stop).
    __pausable__ : bool
        Whether the plan can be paused and resumed by the run engine.
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
