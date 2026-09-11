from __future__ import annotations

import logging
import sys
from collections import deque
from functools import cached_property
from typing import TYPE_CHECKING, Final

from psygnal import Signal

if TYPE_CHECKING:
    from collections.abc import MutableMapping
    from typing import Any, ClassVar

__all__ = [
    "BufferHandler",
    "Loggable",
    "add_handler",
    "log_buffer",
    "remove_handler",
    "set_level",
]

DEFAULT_LEVEL: Final = "INFO"
"""The level the ``redsun`` logger starts at."""

DATE_FORMAT: Final = "%d-%m-%y|%H:%M:%S"
"""How a record's timestamp is written."""

logger = logging.getLogger("redsun")


class GlobalFormatter(logging.Formatter):
    """Custom formatter for log messages."""

    _format: ClassVar[str] = "[%(asctime)s][%(levelname)s]"

    def __init__(self, datefmt: str) -> None:
        super().__init__(datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        fmt = self._format
        message = []
        message.append(record.getMessage())
        record.message = " ".join(message)
        record.asctime = self.formatTime(record, self.datefmt)
        clsname = getattr(record, "clsname", None)
        if clsname:
            fmt += "[%(clsname)s"
        uid = getattr(record, "uid", None)
        if uid:
            fmt += " -> %(uid)s"
        if clsname:
            fmt += "]"
        fmt += ": %(message)s"
        if record.levelno != logging.INFO:
            fmt += " (%(filename)s:%(lineno)d)"
        formatted = fmt % record.__dict__
        return formatted


class ContextualAdapter(logging.LoggerAdapter[logging.Logger]):
    """Adapter that adds class and object context to log messages.

    It expands the ``kwargs`` to inject the object's class name and name into the log record.

    Parameters
    ----------
    logger: logging.Logger
        Logger instance to wrap.
    obj: Any
        The object to add context to.
    """

    logger: logging.Logger

    def __init__(self, logger: logging.Logger, obj: Any) -> None:
        super().__init__(logger, {"obj": obj})
        self.obj = obj

    def process(
        self, msg: str, kwargs: MutableMapping[str, Any]
    ) -> tuple[str, MutableMapping[str, Any]]:
        """Add object context to the log message."""
        clsname = self.obj.__class__.__name__
        extra: dict[str, Any] = kwargs.get("extra", {})
        extra["clsname"] = clsname
        extra["uid"] = getattr(self.obj, "name", None)
        kwargs["extra"] = extra
        return msg, kwargs


class BufferHandler(logging.Handler):
    """Retain the most recent log records, and announce each one as it arrives.

    The records outlive the moment they were emitted, so a consumer built later
    in the session can still show what happened before it existed. The oldest
    are dropped once *capacity* is reached.

    Parameters
    ----------
    capacity : int
        How many records to retain.
    """

    sig_record = Signal(logging.LogRecord)

    def __init__(self, capacity: int = 10_000) -> None:
        super().__init__()
        self._records: deque[logging.LogRecord] = deque(maxlen=capacity)

    @property
    def records(self) -> tuple[logging.LogRecord, ...]:
        """The retained records, oldest first."""
        return tuple(self._records)

    def emit(self, record: logging.LogRecord) -> None:
        """Retain *record* and announce it."""
        self._records.append(record)
        self.sig_record.emit(record)

    def clear(self) -> None:
        """Drop every retained record."""
        self._records.clear()


def set_level(level: int | str) -> None:
    """Set the level of the ``redsun`` logger.

    A named level is matched without regard to case.

    Raises
    ------
    ValueError
        If a name names no level.
    """
    logger.setLevel(level.upper() if isinstance(level, str) else level)


def add_handler(handler: logging.Handler) -> None:
    """Send the ``redsun`` logger's records to *handler* as well.

    A handler carrying no formatter of its own is given the one every other
    destination writes through, so a record reads the same wherever it lands.
    """
    if handler.formatter is None:
        handler.setFormatter(GlobalFormatter(datefmt=DATE_FORMAT))
    logger.addHandler(handler)


def remove_handler(handler: logging.Handler) -> None:
    """Stop sending the ``redsun`` logger's records to *handler*.

    A handler that is not installed is left alone.
    """
    logger.removeHandler(handler)


logger.setLevel(DEFAULT_LEVEL)
add_handler(logging.StreamHandler(sys.stdout))
add_handler(BufferHandler())


def log_buffer() -> BufferHandler:
    """Return the buffer holding this session's log records.

    Raises
    ------
    RuntimeError
        If the logging configuration no longer carries a buffer.
    """
    for handler in logger.handlers:
        if isinstance(handler, BufferHandler):
            return handler
    raise RuntimeError("no BufferHandler is installed on the 'redsun' logger")


class Loggable:
    """Mixin class that adds a logger to a class instance with extra contextual information."""

    @cached_property
    def logger(self) -> logging.LoggerAdapter[logging.Logger]:
        """Logger instance with contextual information."""
        return ContextualAdapter(logging.getLogger("redsun"), self)
