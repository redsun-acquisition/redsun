"""Custom Bluesky plan stubs for redsun plans.

These stubs extend the standard `bluesky.plan_stubs` with redsun-specific
action-based flow control (`wait_for_actions`, `read_while_waiting`).

All functions are generator functions that yield `Msg` objects and are
intended to be composed inside larger Bluesky plans via ``yield from``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import bluesky.plan_stubs as bps
from bluesky.utils import Msg, maybe_await

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Mapping
    from typing import Any, Final, Literal

    from bluesky.protocols import (
        Collectable,
        Descriptor,
        Readable,
    )
    from bluesky.utils import MsgGenerator

    from redsun.engine.actions import SRLatch

SIXTY_FPS: Final[float] = 1.0 / 60.0


def wait_for_actions(
    events: Mapping[str, SRLatch],
    timeout: float = SIXTY_FPS,
    wait_for: Literal["set", "reset"] = "set",
) -> MsgGenerator[tuple[str, SRLatch]]:
    """Wait for any of the given latches to change state.

    Loops at *timeout* intervals until a latch transitions, then returns
    the name and latch that fired. Plan execution yields control on each
    iteration so background tasks continue running normally.

    Parameters
    ----------
    events : Mapping[str, SRLatch]
        Mapping of action names to their `SRLatch` objects.
    timeout : float, optional
        Polling interval in seconds. Default is 1/60 s (60 Hz).
    wait_for : Literal["set", "reset"], optional
        Whether to wait for a latch to be set or reset.
        Default is `"set"`.

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
