from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from ophyd_async.core import StreamResourceInfo

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from typing import Any, ClassVar

    import numpy.typing as npt

    from ._router import FrameRouter


@dataclass(frozen=True, slots=True)
class StreamSpec:
    """Specification of a single frame stream for a data sink channel."""

    data_key: str
    """Channel identity, e.g. the detector's datakey name."""

    shape: tuple[int, ...]
    """Shape of a single frame, e.g. ``(height, width)``."""

    dtype: str
    """NumPy dtype of the frames (e.g. ``"<u2"``)."""

    capacity: int | None
    """Maximum number of frames. `None` means unbounded."""

    @property
    def is_unbounded(self) -> bool:
        """True if the stream grows indefinitely."""
        return self.capacity is None

    def to_resource_info(self) -> StreamResourceInfo:
        """Convert to a `StreamResourceInfo` object."""
        return StreamResourceInfo(
            data_key=self.data_key,
            shape=(self.capacity, *self.shape),
            chunk_shape=self.shape,
            dtype_numpy=self.dtype,
            parameters={},
        )


class SinkFactory(Protocol):
    """Protocol for a factory that creates a per-key frame pusher (sink) for a given data key."""

    mimetype: ClassVar[str]
    """Storage MIME type, e.g. ``"application/x-hdf5"``."""

    extension: ClassVar[str]
    """File extension for the storage backend, e.g. ``"h5"`` for HDF5 files."""

    @abc.abstractmethod
    async def __call__(self, data_key: str) -> AsyncGenerator[None, npt.NDArray[Any]]:
        """Return an async generator that pushes frames to the backend for the given `data_key`."""
        ...


class StorageBackend(SinkFactory, Protocol):
    router: FrameRouter
    """Router for managing streams and their frame counters."""

    @property
    @abc.abstractmethod
    def sealed(self) -> bool:
        """Whether the backend has been sealed (no more streams can be registered)."""

    @property
    @abc.abstractmethod
    def closed(self) -> bool:
        """Whether the backend has been closed (no more frames can be written)."""

    @abc.abstractmethod
    async def register(self, spec: StreamSpec) -> None:
        """Register a new stream with the backend."""
        ...

    @abc.abstractmethod
    async def ensure_open(self) -> None: ...

    @abc.abstractmethod
    async def release(self, data_key: str) -> None: ...

    @abc.abstractmethod
    async def finalize(self) -> None: ...


__all__ = [
    "StreamSpec",
    "SinkFactory",
    "StorageBackend",
]
