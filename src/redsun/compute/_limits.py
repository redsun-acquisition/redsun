"""Limits on the threads native libraries start, which hold for the whole process."""

from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING

from threadpoolctl import threadpool_limits

if TYPE_CHECKING:
    from collections.abc import Callable


def apply_limits(native_threads: int) -> Callable[[], None]:
    """Limit the native thread pools loaded so far, and return what restores them.

    The pools are those `threadpoolctl` finds, such as BLAS and OpenMP, and
    PyTorch's when `torch` is imported. A library imported afterwards keeps
    its own size.
    """
    limiter = threadpool_limits(native_threads)
    restore_libraries: Callable[[], None] = limiter.restore_original_limits
    torch = sys.modules.get("torch")
    if torch is None:
        return restore_libraries
    found = torch.get_num_threads()
    torch.set_num_threads(native_threads)

    def restore() -> None:
        torch.set_num_threads(found)
        restore_libraries()

    return restore


class Limits:
    """The limits one session applies, restored together in reverse order.

    Once restored, applying them again does nothing, so a pool thread
    starting during shutdown cannot leave a limit behind.
    """

    __slots__ = ("lock", "restored", "restores")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.restores: list[Callable[[], None]] = []
        self.restored = False

    def apply(self, native_threads: int) -> None:
        """Limit the native thread pools loaded so far."""
        with self.lock:
            if not self.restored:
                self.restores.append(apply_limits(native_threads))

    def restore(self) -> None:
        """Give back every limit applied, the last first."""
        with self.lock:
            self.restored = True
            while self.restores:
                self.restores.pop()()
