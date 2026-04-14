from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from bluesky.protocols import (
    HasName,
    Movable,
    Readable,
    Subscribable,
    SyncOrAsync,
    Triggerable,
)

T = TypeVar("T")
T_contra = TypeVar("T_contra", contravariant=True)


@runtime_checkable
class AttrR(Readable[T], Subscribable[T], Protocol[T]):
    """Read-only device attribute.

    Composes [`Readable`][bluesky.protocols.Readable] and
    [`Subscribable`][bluesky.protocols.Subscribable] with a convenience
    [`get_value`][] for direct value access without unpacking a reading
    dictionary.

    Structurally compatible with `ophyd_async.core.SignalR`.
    """

    def get_value(self) -> SyncOrAsync[T]:
        """Return the current attribute value directly.

        Returns
        -------
        SyncOrAsync[T]
            The current value, either directly (sync device) or as an
            awaitable (async device).
        """
        ...


@runtime_checkable
class AttrW(HasName, Movable[T_contra], Protocol[T_contra]):
    """Write-only device attribute.

    Structurally compatible with `ophyd_async.core.SignalW`.
    """


@runtime_checkable
class AttrRW(AttrR[T], AttrW[T], Protocol[T]):
    """Read-write device attribute.

    Structurally compatible with `ophyd_async.core.SignalRW`.
    """


@runtime_checkable
class AttrT(HasName, Triggerable, Protocol):
    """Trigger device attribute.

    An executable attribute that fires a discrete action on the device
    and returns a status object tracking its completion.

    Structurally compatible with `ophyd_async.core.SignalX`.
    """
