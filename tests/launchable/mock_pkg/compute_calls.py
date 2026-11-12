"""Functions the process pool tests run in worker processes."""

from __future__ import annotations

import os
import threading

import numpy as np
from numpy.typing import NDArray


def pid() -> int:
    """Return the id of the process running the call."""
    return os.getpid()


def add(a: int, b: int) -> int:
    """Return the sum."""
    return a + b


def crash(code: int) -> None:
    """End the process at once with exit code *code*."""
    os._exit(code)


def double(array: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Return every element doubled."""
    return array * 2


class Unmovable:
    """A value that can be read back only in the process that pickled it."""

    def __reduce__(self) -> tuple[object, tuple[int]]:
        """Rebuild through `rebuild_here`, naming this process."""
        return rebuild_here, (os.getpid(),)


def rebuild_here(pid: int) -> Unmovable:
    """Return an `Unmovable` in process *pid*, and raise in any other."""
    if os.getpid() != pid:
        raise RuntimeError(f"pickled in process {pid}")
    return Unmovable()


def make_unmovable() -> Unmovable:
    """Return a value the caller's process cannot read."""
    return Unmovable()


class HeldLock(Exception):
    """An error carrying a lock, which cannot be pickled."""


def make_lock() -> threading.Lock:
    """Return a lock, which cannot be pickled."""
    return threading.Lock()


def raise_held_lock() -> None:
    """Raise an error that cannot be pickled."""
    raise HeldLock(threading.Lock())
