from __future__ import annotations

from typing import TYPE_CHECKING

from .._base import StorageBackend
from .._router import FrameRouter

if TYPE_CHECKING:
    from typing import Any

    import numpy.typing as npt

    from .._base import StreamSpec


class MemoryBackend(StorageBackend):
    """In memory storage backend."""

    __slots__ = ("router", "_cache", "_sealed", "_closed")

    @property
    def sealed(self) -> bool:
        return self._sealed

    @property
    def closed(self) -> bool:
        return self._closed

    def __init__(self) -> None:
        self.router = FrameRouter()
        self._cache: dict[str, list[npt.NDArray[Any]]] = {}
        self._sealed = False
        self._closed = True

    async def register(self, spec: StreamSpec) -> None:
        if self._sealed:
            raise RuntimeError("Cannot register new streams after sealing.")
        self.router.add(spec)
        self._cache[spec.data_key] = []

    async def ensure_open(self) -> None:
        if self._sealed:
            raise RuntimeError("Cannot open streams after sealing.")
        self._closed = False

    async def release(self, data_key: str) -> None:
        if self.closed:
            raise RuntimeError("Cannot release streams after closing.")
        self.router
