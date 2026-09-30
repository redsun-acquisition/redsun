"""Plan stubs adding action flow control to `bluesky.plan_stubs`.

`wait_for_actions` waits on user actions; `lock`, `unlock` and `lock_wrapper`
lock devices against the user. Every stub is a generator yielding `Msg`
objects, used inside larger plans with `yield from`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import Msg, maybe_await

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Mapping
    from typing import Any, Final, Literal, TypeVar

    from bluesky.protocols import (
        Collectable,
        Descriptor,
        HasName,
        Readable,
    )
    from bluesky.utils import MsgGenerator

    from redsun.engine.actions import SRLatch

    from ._progress import PlanProgress

    T = TypeVar("T")

SIXTY_FPS: Final[float] = 1.0 / 60.0


def wait_for_actions(
    events: Mapping[str, SRLatch],
    poll_interval: float = SIXTY_FPS,
    wait_for: Literal["set", "reset"] = "set",
) -> MsgGenerator[tuple[str, SRLatch]]:
    """Wait until one of the given latches is in the wanted state, and return it.

    Returns the name and the latch as soon as a latch is set, or reset with
    `wait_for="reset"`, whether it was already or changed meanwhile. Of several
    in the wanted state, the one that reached it first is returned, and of
    those that reached it together, the first in *events*. It waits as long as that
    takes. A checkpoint is yielded every *poll_interval* seconds, where the
    plan can be paused, so it cannot be used between `create` and `save`.

    Parameters
    ----------
    events
        Mapping of action names to their `SRLatch` objects.
    poll_interval
        Seconds between two checkpoints, 1/60 s by default.
    wait_for
        Whether to wait for a latch to be set or reset.

    Raises
    ------
    ValueError
        If *events* is empty.
    """
    if not events:
        raise ValueError("no actions to wait on")
    result: tuple[str, SRLatch] | None = None
    while result is None:
        yield from bps.checkpoint()
        result = yield Msg(
            "wait_for_actions",
            None,
            events,
            poll_interval=poll_interval,
            wait_for=wait_for,
        )
    return result


def describe(
    obj: Readable[Any],
) -> MsgGenerator[dict[str, Descriptor]]:
    """Return what `obj.describe()` returns, from inside a plan."""

    async def _describe() -> dict[str, Descriptor]:
        return await maybe_await(obj.describe())

    task: list[asyncio.Task[dict[str, Descriptor]]] = yield from bps.wait_for(
        [_describe]
    )
    result = task[0].result()
    return result


def describe_collect(
    obj: Collectable,
) -> MsgGenerator[dict[str, Descriptor] | dict[str, dict[str, Descriptor]]]:
    """Return what `obj.describe_collect()` returns, from inside a plan."""

    async def _describe_collect() -> (
        dict[str, Descriptor] | dict[str, dict[str, Descriptor]]
    ):
        return await maybe_await(obj.describe_collect())

    task: list[
        asyncio.Task[dict[str, Descriptor] | dict[str, dict[str, Descriptor]]]
    ] = yield from bps.wait_for([_describe_collect])
    result = task[0].result()

    return result


def lock(*devices: HasName) -> MsgGenerator[str]:
    """Lock *devices*, so views disable their controls, and return the lock's token.

    Prefer `lock_wrapper`, which unlocks however the plan ends.
    """
    token = uuid4().hex
    yield Msg("lock", None, *devices, token=token)
    return token


def unlock(token: str) -> MsgGenerator[None]:
    """Release the `lock` that returned *token*."""
    yield Msg("unlock", None, token=token)


def lock_wrapper(plan: MsgGenerator[T], *devices: HasName) -> MsgGenerator[T]:
    """Run *plan* with *devices* locked, unlocking them however it ends.

    ```python
    def scan(stage: Stage, camera: Camera) -> MsgGenerator[None]:
        yield from lock_wrapper(bp.count([camera], 10), stage, camera)
    ```
    """
    token = uuid4().hex

    def locked() -> MsgGenerator[T]:
        yield Msg("lock", None, *devices, token=token)
        return (yield from plan)

    result: T = yield from bpp.finalize_wrapper(locked(), unlock(token))
    return result


def declare_progress(
    name: str, *, parent: str | None = None
) -> MsgGenerator[PlanProgress]:
    """Open a progress scope named *name*, nested under *parent* when given.

    Returns the scope. A view shows it while the plan runs, and the engine
    finishes it when the plan ends.
    """
    scope: PlanProgress = yield Msg("declare_progress", name=name, parent=parent)
    return scope


def update_progress(
    name: str,
    *,
    current: Any = None,
    initial: Any = None,
    target: Any = None,
    unit: str = "unit",
    precision: int | None = None,
    fraction: float | None = None,
    time_elapsed: float | None = None,
    time_remaining: float | None = None,
    done: bool = False,
) -> MsgGenerator[None]:
    """Report how far the scope *name* has got, or finish it with *done*.

    Parameters
    ----------
    current, initial, target
        Where the scope is, started and ends, in *unit*; *target* left out
        when the end is not known.
    fraction
        How far the scope has got, from 0 to 1, in place of the three above.
    precision
        Decimals to show the numbers with.
    """
    yield Msg(
        "update_progress",
        name=name,
        current=current,
        initial=initial,
        target=target,
        unit=unit,
        precision=precision,
        fraction=fraction,
        time_elapsed=time_elapsed,
        time_remaining=time_remaining,
        done=done,
    )
