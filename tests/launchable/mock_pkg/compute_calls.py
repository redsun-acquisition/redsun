"""Functions the process pool tests run in worker processes."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import time
from typing import NoReturn


def pid() -> int:
    """Return the id of the process running the call."""
    return os.getpid()


def add(a: int, b: int) -> int:
    """Return the sum."""
    return a + b


def crash(code: int) -> None:
    """End the process at once with exit code *code*."""
    os._exit(code)


def make_lock() -> threading.Lock:
    """Return a lock, which cannot be pickled."""
    return threading.Lock()


def current_priority() -> int:
    """Return the priority of the process: its class on Windows, its nice value elsewhere."""
    if sys.platform != "win32":
        return os.getpriority(os.PRIO_PROCESS, 0)
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.GetPriorityClass.argtypes = [ctypes.c_void_p]
    return int(kernel32.GetPriorityClass(kernel32.GetCurrentProcess()))


def log_error(message: str) -> None:
    """Log *message* with the traceback of a caught `ZeroDivisionError`."""
    try:
        1 / 0  # noqa: B018
    except ZeroDivisionError:
        logging.getLogger(__name__).exception(message)


def log_debug(message: str) -> None:
    """Log *message* at DEBUG."""
    logging.getLogger(__name__).debug(message)


def spin() -> NoReturn:
    """Loop for ever."""
    while True:
        pass


def spin_for(seconds: float) -> None:
    """Sleep for *seconds*."""
    time.sleep(seconds)


def log_warning(message: str) -> None:
    """Log *message* at WARNING."""
    logging.getLogger(__name__).warning(message)
