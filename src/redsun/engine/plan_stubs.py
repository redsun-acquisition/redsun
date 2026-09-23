"""Plan stubs adding action flow control to `bluesky.plan_stubs`.

`wait_for_actions` and `read_while_waiting` wait on user actions; `lock`,
`unlock` and `lock_wrapper` lock devices against the user. Every stub is a
generator yielding `Msg` objects, used inside larger plans with ``yield from``.
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

    T = TypeVar("T")

SIXTY_FPS: Final[float] = 1.0 / 60.0


def wait_for_actions(
    events: Mapping[str, SRLatch],
    timeout: float = SIXTY_FPS,
    wait_for: Literal["set", "reset"] = "set",
) -> MsgGenerator[tuple[str, SRLatch]]:
    """Wait for any of the given latches to change state.

    Polls every *timeout* seconds until a latch changes, then returns its name
    and latch. The plan yields control on each poll, so background tasks keep
    running.

    Parameters
    ----------
    events : Mapping[str, SRLatch]
        Mapping of action names to their `SRLatch` objects.
    timeout : float, optional
        Polling interval in seconds, 1/60 s by default.
    wait_for : Literal["set", "reset"], optional
        Whether to wait for a latch to be set or reset.

    Returns
    -------
    tuple[str, SRLatch]
        The name and latch that changed state.
    """
    result: tuple[str, SRLatch] | None = None
    while result is None:
        yield from bps.checkpoint()
        result = yield Msg(
            "wait_for_actions", None, events, timeout=timeout, wait_for=wait_for
        )
    return result


def describe(
    obj: Readable[Any],
) -> MsgGenerator[dict[str, Descriptor]]:
    """Gather the descriptor from a `Readable` device.

    Parameters
    ----------
    obj : Readable[Any]
        The device to describe.

    Returns
    -------
    dict[str, Descriptor]
        The descriptor dict returned by ``obj.describe()``.
    """

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
    """Gather descriptors from a `Collectable` device.

    Parameters
    ----------
    obj : Collectable
        The device to describe.

    Returns
    -------
    dict[str, Descriptor] | dict[str, dict[str, Descriptor]]
        The descriptor dict returned by ``obj.describe_collect()``.
    """

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
