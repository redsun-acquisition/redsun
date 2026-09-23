from __future__ import annotations

import contextlib
import heapq
import logging
import os
import shutil
import sys
from collections import deque
from datetime import datetime
from functools import cached_property
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Final

from platformdirs import user_data_dir
from psygnal import Signal

from .utils._paths import session_folder

if TYPE_CHECKING:
    from collections.abc import MutableMapping
    from typing import Any, ClassVar

__all__ = [
    "BufferHandler",
    "Loggable",
    "SessionFileHandler",
    "add_handler",
    "log_buffer",
    "remove_handler",
    "service_of",
    "session_log",
    "set_level",
]

DEFAULT_LEVEL: Final = "INFO"
"""The level the ``redsun`` logger starts at."""

DATE_FORMAT: Final = "%d-%m-%y|%H:%M:%S"
"""How a record's timestamp is written."""

LOG_MAX_BYTES: Final = 10 * 1024 * 1024
"""Size at which a session's log file is rotated."""

LOG_BACKUPS: Final = 5
"""Rotated files kept for one run of a session, beside the current one."""

LOG_RUNS_KEPT: Final = 20
"""Runs of one session whose log files are kept; older runs are deleted."""

APPLICATION_CAPACITY: Final = 10_000
"""Application records the session buffer retains."""

SERVICE_CAPACITY: Final = 2_000
"""Records of each service the session buffer retains."""

SERVICE_LOGGER: Final = "redsun.service"
"""Logger under which each service's records arrive, one child per service."""

logger = logging.getLogger("redsun")


class GlobalFormatter(logging.Formatter):
    """Formatter of ``redsun`` log records."""

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
        # a record rebuilt from a service's output carries no location here
        if record.levelno != logging.INFO and record.lineno:
            fmt += " (%(filename)s:%(lineno)d)"
        formatted = fmt % record.__dict__
        return "\n".join([formatted, *self.context(record)])

    def context(self, record: logging.LogRecord) -> list[str]:
        """Return the traceback and stack lines *record* carries, if any."""
        lines: list[str] = []
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            lines.append(record.exc_text)
        if record.stack_info:
            lines.append(self.formatStack(record.stack_info))
        return lines


class ContextualAdapter(logging.LoggerAdapter[logging.Logger]):
    """Adapter adding an object's class name and name to each record.

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


def service_of(record: logging.LogRecord) -> str | None:
    """Return the name of the service *record* came from, ``None`` for the application."""
    prefix = f"{SERVICE_LOGGER}."
    if not record.name.startswith(prefix):
        return None
    return record.name.removeprefix(prefix).split(".", 1)[0]


class BufferHandler(logging.Handler):
    """Retain the most recent log records, and announce each one as it arrives.

    A consumer built later in the session can still show earlier records.
    Application records and each service's records are kept apart, each
    dropping its oldest when full, so a noisy service drops only its own.

    Parameters
    ----------
    capacity : int
        How many application records to retain.
    service_capacity : int
        How many records of each service to retain.
    """

    sig_record = Signal(logging.LogRecord)

    def __init__(
        self,
        capacity: int = APPLICATION_CAPACITY,
        service_capacity: int = SERVICE_CAPACITY,
    ) -> None:
        super().__init__()
        self._capacity = capacity
        self._service_capacity = service_capacity
        self._records: deque[logging.LogRecord] = deque(maxlen=capacity)
        self._service_records: dict[str, deque[logging.LogRecord]] = {}

    @property
    def capacity(self) -> int:
        """How many application records the buffer retains."""
        return self._capacity

    @property
    def service_capacity(self) -> int:
        """How many records of each service the buffer retains."""
        return self._service_capacity

    @property
    def records(self) -> tuple[logging.LogRecord, ...]:
        """The retained application records, oldest first."""
        return tuple(self._records)

    @property
    def services(self) -> tuple[str, ...]:
        """The services a record has come from, in the order they first did."""
        return tuple(self._service_records)

    def service_records(
        self, service: str | None = None
    ) -> tuple[logging.LogRecord, ...]:
        """Return one service's retained records, or every service's, oldest first."""
        if service is not None:
            return tuple(self._service_records.get(service, ()))
        return tuple(
            heapq.merge(*self._service_records.values(), key=lambda r: r.created)
        )

    def emit(self, record: logging.LogRecord) -> None:
        """Retain *record* with the records of its source, and announce it."""
        service = service_of(record)
        if service is None:
            self._records.append(record)
        else:
            self._service_records.setdefault(
                service, deque(maxlen=self._service_capacity)
            ).append(record)
        self.sig_record.emit(record)

    def clear(self) -> None:
        """Drop every retained record."""
        self._records.clear()
        self._service_records.clear()


class SessionFileHandler(RotatingFileHandler):
    """Write the records of one run of a session to a file of its own.

    The file is under ``logs`` in the session's root, in a folder named after
    the session, then in ``app`` for the application or ``services`` for a
    service, and named after the run: its start time and process. It rotates
    at `LOG_MAX_BYTES`, keeping `LOG_BACKUPS` older files. `move` carries the
    run's files to another root and keeps writing there.

    The application's file, ``<run>.log``, takes no service records, and
    opening it deletes the files of all but the session's `LOG_RUNS_KEPT` most
    recent runs. A service's file, ``<run>.<service>.log``, belongs to *run*,
    is installed with ``add_handler(handler, service)``, and is created when
    the service first logs.

    Parameters
    ----------
    session : str
        Name of the session.
    service : str | None
        The service whose records the file holds, ``None`` for the application.
    run : str | None
        The run, as the application handler's `run`. ``None`` starts a new
        run.
    root : Path | None
        Root the session writes under, as the path provider's `base_dir`.
        ``None`` is the user data directory.
    """

    def __init__(
        self,
        session: str,
        service: str | None = None,
        run: str | None = None,
        *,
        root: Path | None = None,
    ) -> None:
        self._session = session
        self._service = service
        self._root = root or Path(user_data_dir("redsun", appauthor=False))
        folder = self._folder(self._root)
        folder.mkdir(parents=True, exist_ok=True)
        if run is None:
            started = datetime.now().astimezone().strftime("%Y-%m-%dT%H-%M-%S")
            run = f"{started}_{os.getpid()}"
        if service is None:
            _delete_old_runs(folder, keep=LOG_RUNS_KEPT - 1)
            _delete_old_runs(folder.with_name("services"), keep=LOG_RUNS_KEPT - 1)
        self.run = run
        super().__init__(
            folder / (f"{run}.log" if service is None else f"{run}.{service}.log"),
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUPS,
            encoding="utf-8",
            delay=service is not None,
        )
        if service is None:
            self.addFilter(lambda record: service_of(record) is None)

    def _folder(self, root: Path) -> Path:
        return (
            root
            / "logs"
            / session_folder(self._session)
            / ("app" if self._service is None else "services")
        )

    @property
    def root(self) -> Path:
        """Root the run's files are under."""
        return self._root

    def move(self, root: Path) -> None:
        """Carry the run's files under *root* and keep writing there.

        Nothing happens when *root* is the current one.
        """
        root = Path(root).expanduser()
        if root == self._root:
            return
        self.acquire()
        try:
            was_open = self.stream is not None
            if self.stream is not None:
                self.stream.close()
                self.stream = None
            folder = self._folder(root)
            folder.mkdir(parents=True, exist_ok=True)
            for path in self.files:
                shutil.move(path, folder / path.name)
            self.baseFilename = str(folder / Path(self.baseFilename).name)
            self._root = root
            if was_open:
                self.stream = self._open()
        finally:
            self.release()

    @property
    def files(self) -> list[Path]:
        """The files of this run, oldest records first."""
        current = Path(self.baseFilename)
        rotated = [
            current.with_name(f"{current.name}.{index}")
            for index in range(self.backupCount, 0, -1)
        ]
        return [path for path in (*rotated, current) if path.exists()]


def _delete_old_runs(folder: Path, keep: int) -> None:
    """Delete the log files of every run in *folder* but the *keep* most recent."""
    runs = sorted({path.name.split(".", 1)[0] for path in folder.glob("*.log*")})
    for run in runs[: max(len(runs) - keep, 0)]:
        for path in folder.glob(f"{run}.*"):
            # a run still open in another process keeps its file on Windows
            with contextlib.suppress(OSError):
                path.unlink()


def set_level(level: int | str) -> None:
    """Set the level of the ``redsun`` logger.

    Level names are case-insensitive.

    Raises
    ------
    ValueError
        If a name names no level.
    """
    logger.setLevel(level.upper() if isinstance(level, str) else level)


def add_handler(handler: logging.Handler, service: str | None = None) -> None:
    """Send the ``redsun`` logger's records to *handler* as well.

    With a *service*, only that service's records reach *handler*. A handler
    without a formatter gets the shared one, so records read the same
    everywhere.
    """
    if handler.formatter is None:
        handler.setFormatter(GlobalFormatter(datefmt=DATE_FORMAT))
    _logger_for(service).addHandler(handler)


def remove_handler(handler: logging.Handler, service: str | None = None) -> None:
    """Stop sending the records `add_handler` sent to *handler*.

    A handler that is not installed is left alone.
    """
    _logger_for(service).removeHandler(handler)


def _logger_for(service: str | None) -> logging.Logger:
    """Return the ``redsun`` logger, or the one a *service*'s records arrive on."""
    return (
        logger if service is None else logging.getLogger(f"{SERVICE_LOGGER}.{service}")
    )


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


def session_log(service: str | None = None) -> SessionFileHandler | None:
    """Return the handler writing this run's log file, if a session opened one.

    With a *service*, the handler writing that service's file.
    """
    for handler in _logger_for(service).handlers:
        if isinstance(handler, SessionFileHandler):
            return handler
    return None


class Loggable:
    """Mixin giving instances a logger that names them in each record."""

    @cached_property
    def logger(self) -> logging.LoggerAdapter[logging.Logger]:
        """Logger naming this instance in each record."""
        return ContextualAdapter(logging.getLogger("redsun"), self)
