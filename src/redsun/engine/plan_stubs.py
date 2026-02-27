"""Custom Bluesky plan stubs for redsun plans.

These stubs extend the standard `bluesky.plan_stubs` with redsun-specific
operations such as device-cache management (`stash`, `clear_cache`) and
action-based flow control (`wait_for_actions`, `read_while_waiting`).

All functions are generator functions that yield `Msg` objects and are
intended to be composed inside larger Bluesky plans via ``yield from``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import bluesky.plan_stubs as bps
from bluesky.protocols import Triggerable
from bluesky.utils import Msg, maybe_await, short_uid

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Mapping, Sequence
    from typing import Any, Final, Literal

    from bluesky.protocols import (
        Collectable,
        Descriptor,
        Movable,
        Readable,
        Reading,
        Status,
    )
    from bluesky.utils import MsgGenerator

    from redsun.device.protocols import HasCache
    from redsun.engine.actions import SRLatch

SIXTY_FPS: Final[float] = 1.0 / 60.0


def set_property(
    obj: Movable[Any],
    value: Any,
    /,
    propr: str,
    timeout: float | None = None,
) -> MsgGenerator[Status]:
    """Set a property of a `Movable` object and wait for completion.

    Parameters
    ----------
    obj : Movable[Any]
        The movable object whose property will be set.
    value : Any
        The value to set.
    propr : str
        The property name to set (keyword-only).
    timeout : float | None, optional
        Maximum time in seconds to wait for completion.
        None means wait indefinitely. Default is None.

    Yields
    ------
    Msg
        A ``set`` message followed by a ``wait`` message.

    Returns
    -------
    Status
        The status object returned by the ``set`` operation.
    """
    group = str(uuid.uuid4())
    status: Status = yield Msg("set", obj, value, group=group, propr=propr)
    yield Msg("wait", None, group=group, timeout=timeout)
    return status


def wait_for_actions(
    events: Mapping[str, SRLatch],
    timeout: float = 0.001,
    wait_for: Literal["set", "reset"] = "set",
) -> MsgGenerator[tuple[str, SRLatch] | None]:
    """Wait for any of the given latches to change state.

    Plan execution blocks until one latch transitions; background tasks
    continue running normally.

    Parameters
    ----------
    events : Mapping[str, SRLatch]
        Mapping of action names to their `SRLatch` objects.
    timeout : float, optional
        Maximum time in seconds to wait before returning None.
        Default is 0.001 seconds.
    wait_for : Literal["set", "reset"], optional
        Whether to wait for a latch to be set or reset.
        Default is ``"set"``.

    Returns
    -------
    tuple[str, SRLatch] | None
        The name and latch that changed state, or None if the timeout
        elapsed without any latch transitioning.
    """
    ret: tuple[str, SRLatch] | None = yield Msg(
        "wait_for_actions", None, events, timeout=timeout, wait_for=wait_for
    )
    return ret


def read_while_waiting(
    objs: Sequence[Readable[Any]],
    events: Mapping[str, SRLatch],
    stream_name: str = "primary",
    refresh_period: float = SIXTY_FPS,
    wait_for: Literal["set", "reset"] = "set",
) -> MsgGenerator[tuple[str, SRLatch]]:
    """Repeatedly trigger and read devices until an action latch changes state.

    On each iteration the plan triggers and reads all objects in *objs*, then
    checks whether any latch in *events* has changed state.  The loop repeats
    at *refresh_period* until a latch transitions.

    Parameters
    ----------
    objs : Sequence[Readable[Any]]
        Devices to trigger and read on each iteration.
    events : Mapping[str, SRLatch]
        Mapping of action names to `SRLatch` objects to monitor.
    stream_name : str, optional
        Name of the Bluesky stream to collect data into.
        Default is ``"primary"``.
    refresh_period : float, optional
        Polling period in seconds. Default is 1/60 s (60 Hz).
    wait_for : Literal["set", "reset"], optional
        Whether to wait for a latch to be set or reset.
        Default is ``"set"``.

    Returns
    -------
    tuple[str, SRLatch]
        The name and latch that unblocked the loop.
    """
    event: tuple[str, SRLatch] | None = None
    while event is None:
        yield from bps.checkpoint()
        event = yield from wait_for_actions(
            events, timeout=refresh_period, wait_for=wait_for
        )
        yield from bps.trigger_and_read(objs, name=stream_name)
    return event


def read_and_stash(
    objs: Sequence[Readable[Any]],
    cache_objs: Sequence[HasCache],
    *,
    stream: str = "primary",
    group: str | None = None,
    wait: bool = False,
) -> MsgGenerator[dict[str, Reading[Any]]]:
    """Trigger, read, and stash readings from one or more devices.

    Triggers all `Triggerable` devices in *objs*, reads each device, stashes
    the reading into the corresponding `HasCache` object in *cache_objs*, and
    emits a Bluesky ``create``/``save`` pair to record the event.

    Parameters
    ----------
    objs : Sequence[Readable[Any]]
        Devices to read from.
    cache_objs : Sequence[HasCache]
        Cache objects paired with *objs* (same order) to stash readings into.
    stream : str, optional
        Bluesky stream name. Default is ``"primary"``.
    group : str | None, optional
        Identifier for the stash group. Auto-generated if None.
    wait : bool, optional
        Whether to wait for all stash operations to complete before
        returning. Default is False.

    Returns
    -------
    dict[str, Reading[Any]]
        Combined readings from all devices.
    """

    def inner_trigger() -> MsgGenerator[None]:
        grp = short_uid("trigger")
        no_wait = True
        for obj in objs:
            if isinstance(obj, Triggerable):
                no_wait = False
                yield from bps.trigger(obj, group=grp)
        if not no_wait:
            yield from bps.wait(group=grp)

    ret: dict[str, Reading[Any]] = {}

    if any(isinstance(obj, Triggerable) for obj in objs):
        yield from inner_trigger()

    yield from bps.create(stream)
    for obj, cache_obj in zip(objs, cache_objs):
        reading = yield from bps.read(obj)
        yield from stash(cache_obj, reading, group=group, wait=wait)
        ret.update(reading)

    yield from bps.save()
    return ret


def stash(
    obj: HasCache,
    reading: dict[str, Reading[Any]],
    *,
    group: str | None,
    wait: bool,
) -> MsgGenerator[None]:
    """Stash a reading into a `HasCache` device.

    Parameters
    ----------
    obj : HasCache
        The cache object to stash the reading into.
    reading : dict[str, Reading[Any]]
        The reading to stash, typically from `bps.read`.
    group : str | None
        Identifier for the stash group. A unique id is generated if None.
    wait : bool
        Whether to wait for the stash operation to complete.
    """
    if not group:
        group = short_uid("stash")

    yield Msg("stash", obj, reading, group=group)
    if wait:
        yield from bps.wait(group=group)


def clear_cache(
    obj: HasCache, *, group: str | None = None, wait: bool = False
) -> MsgGenerator[None]:
    """Clear the cache of a `HasCache` device.

    Parameters
    ----------
    obj : HasCache
        The cache object to clear.
    group : str | None, optional
        Identifier for the clear operation. Auto-generated if None.
    wait : bool, optional
        Whether to wait for the clear operation to complete.
        Default is False.
    """
    if not group:
        group = short_uid("clear_cache")

    yield Msg("clear_cache", obj, group=group)
    if wait:
        yield from bps.wait(group=group)


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
