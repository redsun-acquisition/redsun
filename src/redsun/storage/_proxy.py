# SPDX-License-Identifier: Apache-2.0
# The design of this module is heavily inspired by ophyd-async
# (https://github.com/bluesky/ophyd-async), developed by the Bluesky collaboration.
# ophyd-async is licensed under the BSD 3-Clause License.
# No source code from ophyd-async has been copied; the StorageProxy protocol and
# opt-in descriptor pattern were studied and independently re-implemented for redsun.

"""StorageProxy protocol and StorageDescriptor for device-side storage access."""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    _ProtocolMeta,
    overload,
    runtime_checkable,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    import numpy as np
    from bluesky.protocols import StreamAsset

    from redsun.storage._base import FrameSink


@runtime_checkable
class StorageProxy(Protocol):
    """Protocol that devices use to interact with a storage backend.

    [`Writer`][redsun.storage.Writer] instances implement this protocol,
    so device code remains independent of the concrete backend.

    Devices access the backend via their `storage` attribute, which is
    `None` when no backend has been configured for the session.
    """

    def update_source(
        self,
        name: str,
        dtype: np.dtype[np.generic],
        shape: tuple[int, ...],
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Register or update a data source on the backend."""
        ...

    def prepare(self, name: str, capacity: int = 0) -> FrameSink:
        """Prepare the backend for *name* and return a [`FrameSink`][redsun.storage.FrameSink]."""
        ...

    def kickoff(self) -> None:
        """Open the storage backend."""
        ...

    def complete(self, name: str) -> None:
        """Signal that *name* has finished writing."""
        ...

    def get_indices_written(self, name: str | None = None) -> int:
        """Return the number of frames written for *name*."""
        ...

    def collect_stream_docs(
        self,
        name: str,
        indices_written: int,
    ) -> Iterator[StreamAsset]:
        """Yield Bluesky stream documents for *name*."""
        ...


class _HasStorageMeta(_ProtocolMeta):
    """Metaclass for [HasStorage][redsun.storage.HasStorage] that overrides `__instancecheck__`."""

    def __instancecheck__(cls, instance: object) -> bool:
        return any(
            isinstance(vars(c).get("storage"), StorageDescriptor)
            for c in type(instance).__mro__
        )


@runtime_checkable
class HasStorage(Protocol, metaclass=_HasStorageMeta):
    """Protocol for devices that have opted in to storage."""

    storage: StorageProxy


class StorageDescriptor:
    """Descriptor that manages the `storage` slot on a device.

    The private attribute name is derived from the descriptor's own name
    at class-creation time via `__set_name__` (e.g. a class attribute
    named `storage` produces a backing attribute `_storage`).  Reading
    and writing go through `object.__getattribute__` and
    `object.__setattr__` rather than `__dict__` access, so the descriptor
    works correctly on classes that define `__slots__` as long as the
    backing slot is declared.

    This descriptor is public so users can reference it explicitly in
    custom device classes:

    ```python
    from redsun.device import Device
    from redsun.storage import StorageDescriptor


    class MyDevice(Device):
        storage = StorageDescriptor()
    ```
    """

    def __init__(self) -> None:
        # Fallback name used when the descriptor is instantiated outside a
        # class body (e.g. in tests) before __set_name__ is called.
        self._private_name: str = "_storage"

    def __set_name__(self, owner: type, name: str) -> None:
        self._private_name = f"_{name}"

    @overload
    def __get__(self, obj: None, objtype: type) -> StorageDescriptor: ...

    @overload
    def __get__(self, obj: Any, objtype: type | None) -> StorageProxy | None: ...

    def __get__(
        self,
        obj: Any,
        objtype: type | None = None,
    ) -> StorageDescriptor | StorageProxy | None:
        if obj is None:
            return self
        try:
            result: StorageProxy | None = object.__getattribute__(
                obj, self._private_name
            )
        except AttributeError:
            result = None
        return result

    def __set__(self, obj: Any, value: StorageProxy | None) -> None:
        object.__setattr__(obj, self._private_name, value)


def require_storage(storage: StorageProxy | None, name: str = "") -> StorageProxy:
    """Return *storage* narrowed to [`StorageProxy`][redsun.storage.StorageProxy], raising if ``None``.

    Use this in device methods that may only be called after the container
    has injected the storage backend (i.e. after ``prepare()``).  It avoids
    scattering ``assert self.storage is not None`` calls throughout device
    code while still giving mypy a fully-narrowed type.

    Parameters
    ----------
    storage:
        The value of ``self.storage``.
    name:
        Optional device name included in the error message.

    Returns
    -------
    StorageProxy
        *storage* unchanged, narrowed to non-optional.

    Raises
    ------
    RuntimeError
        If *storage* is ``None``.

    Examples
    --------
    ```python
    from redsun.storage import require_storage

    class MyDetector(Device):
        storage = StorageDescriptor()

        def kickoff(self) -> Status:
            backend = require_storage(self.storage, self.name)
            backend.kickoff()
            ...
    ```
    """
    if storage is None:
        device_info = f" for device '{name}'" if name else ""
        raise RuntimeError(
            f"No storage backend configured{device_info}. "
            "Ensure prepare() is called before this method."
        )
    return storage
