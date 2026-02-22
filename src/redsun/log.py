from __future__ import annotations

import logging
import logging.config
from functools import cached_property

__all__ = ["Loggable"]

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, MutableMapping

    _LoggerAdapter = logging.LoggerAdapter[logging.Logger]
else:
    _LoggerAdapter = logging.LoggerAdapter


class GlobalFormatter(logging.Formatter):
    """Custom formatter for log messages."""

    _format = "[%(asctime)s][%(levelname)s]"

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


class ContextualAdapter(_LoggerAdapter):
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


class InfoFilter(logging.Filter):
    def __init__(self, name: str = "") -> None:
        super().__init__(name)

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.INFO


class DebugFilter(logging.Filter):
    def __init__(self, name: str = "") -> None:
        super().__init__(name)

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.INFO


config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"()": lambda: GlobalFormatter(datefmt="%d-%m-%y|%H:%M:%S")}
    },
    "filters": {
        "info_filter": {"()": InfoFilter},
        "debug_filter": {"()": DebugFilter},
    },
    "handlers": {
        "info": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "default",
            "stream": "ext://sys.stdout",
            "filters": ["info_filter"],
        },
        "debug": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "default",
            "stream": "ext://sys.stdout",
            "filters": ["debug_filter"],
        },
    },
    "loggers": {
        "redsun": {"level": "DEBUG", "propagate": True, "handlers": ["info", "debug"]}
    },
}

logging.config.dictConfig(config)
logger = logging.getLogger("redsun")


class Loggable:
    """Mixin class that adds a logger to a class instance with extra contextual information."""

    @cached_property
    def logger(self) -> _LoggerAdapter:
        """Logger instance with contextual information."""
        return ContextualAdapter(logging.getLogger("redsun"), self)
