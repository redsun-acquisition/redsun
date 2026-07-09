from __future__ import annotations

from typing import TYPE_CHECKING

from redsun.log import Loggable
from redsun.storage import StorageBackend

from .._router import FrameRouter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from typing import Any

    import numpy.typing as npt
    from ophyd_async.core import PathProvider

    from redsun.storage import StreamSpec


class MemoryBackend(StorageBackend, Loggable):
    """In memory storage backend.

    Used for testing (for now).
    """

    __slots__ = ("router", "_cache", "_sealed", "_closed", "path_provider")

    mimetype = "application/x-memory"

    extension = ""

    @property
    def sealed(self) -> bool:
        return self._sealed

    def __init__(self, path_provider: PathProvider) -> None:
        self.router = FrameRouter()
        self.path_provider = path_provider
        self._cache: dict[str, list[npt.NDArray[Any]]] = {}
        self._sealed = False

    async def _frame_pusher(
        self, data_key: str
    ) -> AsyncGenerator[None, npt.NDArray[Any]]:
        """Create a generator that accepts frames and stores them in memory for the given data key."""
        await self.ensure_open()
        try:
            while True:
                frame = yield
                self._cache[data_key].append(frame)
                self.router.mark_written(data_key)
        except GeneratorExit:
            await self.release(data_key)

    async def __call__(self, data_key: str) -> AsyncGenerator[None, npt.NDArray[Any]]:
        gen = self._frame_pusher(data_key)
        await anext(gen)
        return gen

    async def register(self, spec: StreamSpec) -> None:
        if self.sealed:
            raise RuntimeError("Cannot register new streams after sealing.")
        self.router.add(spec)
        self._cache[spec.data_key] = list()

    async def ensure_open(self) -> None:
        if not self.sealed:
            self._sealed = True
            self.logger.info("Storage sealed.")

    async def release(self, data_key: str) -> None:
        self.router.pop(data_key)
        del self._cache[data_key]
        self.logger.info("Closing stream for data_key: %s", data_key)
        if len(self.router.spec) == 0:
            self._sealed = False
            self.logger.info("All streams closed. Storage unsealed.")
