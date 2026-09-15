"""Logging helpers for the experimental layer.

A copy of `redsun.log` rather than a re-export, so this package depends on
nothing in the supported layer and can replace it when that one is retired.
The duplication is deliberate and is expected to end there.

What is not copied is the configuration `redsun.log` performs at import,
setting the level and installing a handler. Both modules write to the same
``redsun`` logger, so doing it here as well would put a second handler on it
and print every record twice for as long as both exist. Whichever module
survives keeps those two lines.
"""

from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import MutableMapping
    from typing import Any, ClassVar

__all__ = ["Loggable", "add_handler", "remove_handler", "set_level"]

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
    obj: object
        The object to add context to.
    """

    logger: logging.Logger

    def __init__(self, logger: logging.Logger, obj: object) -> None:
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


class Loggable:
    """Mixin class that adds a logger to a class instance with extra contextual information."""

    @cached_property
    def logger(self) -> logging.LoggerAdapter[logging.Logger]:
        """Logger instance with contextual information."""
        return ContextualAdapter(logging.getLogger("redsun"), self)
