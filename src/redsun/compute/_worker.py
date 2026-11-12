"""What a worker process runs when it starts: its log queue, native thread limit and priority."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import traceback
from ctypes import wintypes
from logging.handlers import QueueHandler
from typing import TYPE_CHECKING, Final

from threadpoolctl import threadpool_limits

from ..log import text_copy

if TYPE_CHECKING:
    from logging import LogRecord
    from multiprocessing.queues import Queue

    from ._settings import Priority

BELOW_NORMAL_PRIORITY_CLASS: Final = 0x4000
HIGH_PRIORITY_CLASS: Final = 0x80

logger = logging.getLogger("redsun")


def set_priority(priority: Priority) -> None:
    """Set the priority of this process.

    Raises
    ------
    OSError
        If the system refuses the priority.
    """
    if priority == "normal":
        return
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        flag = BELOW_NORMAL_PRIORITY_CLASS if priority == "low" else HIGH_PRIORITY_CLASS
        if not kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), flag):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.setpriority(os.PRIO_PROCESS, 0, 10 if priority == "low" else -10)


class WorkerLogHandler(QueueHandler):
    """Send a worker's log records to the main process as text."""

    def prepare(self, record: LogRecord) -> LogRecord:
        """Return *record* with its message and traceback as text."""
        return text_copy(record)


def prepare_worker(
    queue: Queue[LogRecord], level: int, priority: Priority, native_threads: int
) -> None:
    """Make this process a worker: log into *queue*, limit native threads, set the priority.

    Never raises: an exception in a pool's initializer breaks the pool.
    """
    try:
        root = logging.getLogger()
        root.handlers[:] = [WorkerLogHandler(queue)]
        root.setLevel(level)
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)
        logging.getLogger("multiprocessing").propagate = False
        threadpool_limits(native_threads)
        try:
            set_priority(priority)
        except OSError as error:
            logger.warning(f"Worker process kept normal priority: {error}")
    except Exception:  # noqa: BLE001 - the initializer must not break the pool
        traceback.print_exc(file=sys.stderr)
