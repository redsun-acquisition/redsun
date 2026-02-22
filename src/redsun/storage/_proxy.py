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

    Devices access the backend via their ``storage`` attribute. The container
    injects a [`Writer`][redsun.storage.Writer] instance before any acquisition
    begins; if no storage section is present in the session configuration the
    device's ``storage`` attribute is never set and accessing it will raise
    ``AttributeError``.
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
    """Descriptor that manages the ``storage`` slot on a device.

    The private attribute name is derived from the descriptor's own name
    at class-creation time via ``__set_name__`` (e.g. a class attribute
    named ``storage`` produces a backing attribute ``_storage``).  Reading
    and writing go through ``object.__getattribute__`` and
    ``object.__setattr__`` rather than ``__dict__`` access, so the descriptor
    works correctly on classes that define ``__slots__`` as long as the
    backing slot is declared.

    From the **typing perspective**, ``storage`` is always a
    [`StorageProxy`][redsun.storage.StorageProxy] — the descriptor promises
    that the container will inject a backend before any acquisition method is
    called.  At runtime, reading ``storage`` before injection raises
    ``AttributeError``; device code that must guard against a sessionless
    configuration should check via ``hasattr(self, 'storage')`` rather than
    comparing against ``None``.

    This descriptor is public so users can reference it explicitly in
    custom device classes:

    ```python
    from redsun.device import Device
    from redsun.storage import StorageDescriptor


    class MyDevice(Device):
        storage = StorageDescriptor()

        def prepare(self, ...) -> Status:
            if not hasattr(self, 'storage'):
                raise RuntimeError("No storage backend configured.")
            self.storage.update_source(...)
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
    def __get__(self, obj: Any, objtype: type | None) -> StorageProxy: ...

    def __get__(
        self,
        obj: Any,
        objtype: type | None = None,
    ) -> StorageDescriptor | StorageProxy:
        if obj is None:
            return self
        return object.__getattribute__(obj, self._private_name)  # type: ignore[no-any-return]

    def __set__(self, obj: Any, value: StorageProxy) -> None:
        object.__setattr__(obj, self._private_name, value)
