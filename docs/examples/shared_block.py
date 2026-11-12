"""The shared block of the guide "How to run background processing"."""

from __future__ import annotations

from contextlib import suppress
from functools import partial
from multiprocessing import shared_memory
from typing import TYPE_CHECKING

import numpy as np
from event_model import DocumentRouter
from psygnal import Signal

from redsun.compute import ProcessExecutor  # noqa: TC001
from redsun.log import Loggable

if TYPE_CHECKING:
    from event_model import Event, EventDescriptor, RunStart, RunStop
    from numpy.typing import NDArray


# --8<-- [start:function]
def fit_stack(name: str, shape: tuple[int, ...], dtype: str) -> NDArray[np.float64]:
    block = shared_memory.SharedMemory(name=name)
    stack = np.ndarray(shape, dtype, block.buf)
    try:
        return stack.mean(axis=0)
    finally:
        del stack
        block.close()


# --8<-- [end:function]
# --8<-- [start:presenter]
class StackPresenter(DocumentRouter, Loggable):
    sig_fit = Signal(object)

    def __init__(
        self,
        name: str,
        executor: ProcessExecutor,
        *,
        source: str = "camera",
        frames: int = 40,
    ) -> None:
        super().__init__()
        self.name = name
        self.source = source
        self._executor = executor
        self._count = frames
        self._next = 0
        self._block: shared_memory.SharedMemory | None = None
        self._stack: NDArray[np.generic] | None = None

    # --8<-- [end:presenter]
    # --8<-- [start:documents]
    def start(self, doc: RunStart) -> RunStart:
        self._next = 0
        return doc

    def descriptor(self, doc: EventDescriptor) -> EventDescriptor:
        key = doc["data_keys"][self.source]
        shape = (self._count, *(int(n or 0) for n in key["shape"]))
        dtype = np.dtype(key.get("dtype_numpy", "uint16"))
        size = max(1, int(np.prod(shape)) * dtype.itemsize)
        self._block = shared_memory.SharedMemory(create=True, size=size)
        self._stack = np.ndarray(shape, dtype, self._block.buf)
        return doc

    def event(self, doc: Event) -> Event:
        if self._stack is not None and self._next < self._count:
            self._stack[self._next] = doc["data"][self.source]
            self._next += 1
        return doc

    def stop(self, doc: RunStop) -> RunStop:
        if self._block is None or self._stack is None:
            return doc
        block, self._block = self._block, None
        shape, dtype = self._stack.shape, self._stack.dtype.str
        self._stack = None
        future = self._executor.submit(fit_stack, block.name, shape, dtype)
        future.then(partial(self._publish, block), partial(self._report, block))
        return doc

    # --8<-- [end:documents]
    # --8<-- [start:release]
    def _publish(
        self, block: shared_memory.SharedMemory, fit: NDArray[np.float64]
    ) -> None:
        self._release(block)
        self.sig_fit.emit(fit)

    def _report(self, block: shared_memory.SharedMemory, error: BaseException) -> None:
        self._release(block)
        self.logger.warning(f"No fit for this run: {error}")

    def _release(self, block: shared_memory.SharedMemory) -> None:
        block.close()
        with suppress(FileNotFoundError):
            block.unlink()


# --8<-- [end:release]
