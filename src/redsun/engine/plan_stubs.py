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
    obj: Movable[Any]
        The Movable object to set.
    value: Any
        The value to set the property to.
    propr: str, keyword-only
        The property name to set.
    timeout: float, keyword-only, optional
        The maximum time (in seconds) to wait for the operation to complete.
        Default is None (wait indefinitely).

    Yields
    ------
    Msg
        Yields two messages:
        - `Msg("set", obj, value, propr=propr)`: to set the property.
        - `Msg("wait", None, timeout=timeout)`: to wait for the operation to complete.

    Returns
    -------
    Status
        The status object returned by the `set` method.
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
    """Wait for any of the given input latches to be set or reset.

    Plan execution will be blocked until one of the latches changes state; but
    background tasks will proceed as usual.

    Parameters
    ----------
    events: Mapping[str, SRLatch]
        A mapping of event names to SRLatch objects to wait for.

    timeout: float, optional
        The maximum time (in seconds) to wait for a latch to change state.
        Default is 0.001 seconds.

    wait_for: Literal["set", "reset"], optional
        Whether to wait for the latch to be set or reset.
        Default is "set".

    Returns
    -------
    tuple[str, SRLatch] | None
        A tuple containing the name and latch that changed state to unblock the plan;
        None if timeout occurred before any latch changed state.
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
    """Read a list of `Readable` objects while waiting for actions.

    Parameters
    ----------
    objs : ``Sequence[Readable[Any]]``
        The objects to trigger and read.
    events : ``Mapping[str, SRLatch]``
        A mapping of event names to SRLatch objects to wait for.
        Each latch represents an action that can unblock the plan.
    stream_name : ``str``, optional
        The name of the stream to collect data into.
        Default is "primary".
    refresh_period : ``float``, optional
        The period (in seconds) to refresh the triggering and reading.
        Default is 60 Hz (1/60 s).
    wait_for : ``Literal["set", "reset"]``, optional
        Whether to wait for the latch to be set or reset.
        Default is "set".

    Yields
    ------
    Msg
        Messages to wait and trigger/read the objects.

    Returns
    -------
    tuple[str, SRLatch]
        The latch that changed state to unblock the plan.
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
    """Take a reading from one or more Readable devices and stash the readings.

    Parameters
    ----------
    objs: Sequence[Readable[Any]]
        The Readable devices to read from.
    cache_obj: HasCache
        The cache object to stash the readings into.
    stream: str, optional
        The name of the stream to collect data into.
        Default is "primary".
    group: str | None, optional
        An optional identifier for the stash operation.
        If None, a unique identifier will be generated for each call.
    wait: bool, optional
        Whether to wait for the stashing operation to complete.
        Default is False.
    """

    def inner_trigger() -> MsgGenerator[None]:
        grp = short_uid("trigger")
        no_wait = True
        for obj in objs:
            if isinstance(obj, Triggerable):
                no_wait = False
                yield from bps.trigger(obj, group=grp)
        # Skip 'wait' if none of the devices implemented a trigger method.
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
    """Take a reading from a Readable device and stash the reading.

    Parameters
    ----------
    obj: HasCache
        The cache object to stash the reading into.
    name: str
        Name of the device associated with the reading (accessible via `obj.name`).
    reading: dict[str, Reading[Any]]
        The reading to stash, typically obtained from a call to `bps.read()`.
    stash: HasCache
        The cache object to stash the reading into.
    group: str | None
        An optional identifier for the stash operation.
        If None, a unique identifier will be generated for each call.
    wait: bool
        Whether to wait for the stashing operation to complete.
    """
    if not group:
        group = short_uid("stash")

    yield Msg("stash", obj, reading, group=group)
    if wait:
        yield from bps.wait(group=group)


def clear_cache(
    obj: HasCache, *, group: str | None = None, wait: bool = False
) -> MsgGenerator[None]:
    """Clear the cache of a `HasCache` object.

    Parameters
    ----------
    obj: `HasCache`
        The cache object to clear.
    group: str | None
        An optional identifier for the clear operation.
        If None, a unique identifier will be generated for each call.
    wait: bool
        Whether to wait for the clear operation to complete.
    """
    if not group:
        group = short_uid("clear_cache")

    yield Msg("clear_cache", obj, group=group)
    if wait:
        yield from bps.wait(group=group)


def describe(
    obj: Readable[Any],
) -> MsgGenerator[dict[str, Descriptor]]:
    """Gather the descriptor from a Readable object.

    Parameters
    ----------
    objs : Readable[Any]
        Object to describe.

    Returns
    -------
    list[dict[str, Descriptor]]
        A list of descriptors from each device.
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
    """Gather descriptors from a Collectable object.

    Parameters
    ----------
    obj : Collectable
        Object to describe.

    Returns
    -------
    dict[str, Descriptor]
        A dictionary of descriptors from the Collectable object.
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
