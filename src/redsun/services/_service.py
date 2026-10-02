from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Final, TypeAlias

from psygnal import Signal

from redsun.log import SERVICE_LOGGER, logger

from ._process import LEVEL_VARIABLE, NAME_VARIABLE, PREFIX_VARIABLE, READY_VARIABLE
from ._transports import CHANNEL_ACCESS, TRANSPORTS

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

STARTUP_TIMEOUT: Final = 15.0
"""Seconds a launched service has to print its readiness line."""

STOP_TIMEOUT: Final = 10.0
"""Seconds each step of `Service.stop` waits, unless the service gives its own."""

TAIL_LINES: Final = 20
"""Lines of a service's latest output kept to explain an unexpected exit."""

# without it, services started from several threads at once could draw one
# port twice, lose an address list entry, or copy a changing environment
launch_lock = threading.Lock()
"""Held while a service reserves its transport and copies the environment."""

PVXS_LINE: Final = re.compile(
    r"^(?P<time>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\.(?P<fraction>\d+) "
    r"(?P<level>CRIT|ERR|WARN|INFO|DEBUG) (?P<name>pvxs(?:\.\w+)*) (?P<message>.*)$"
)
"""A line `pvxs`, the library under a PVAccess server, writes to standard error.

It bypasses Python logging, so the level, time and logger name are read
back from the text.
"""

PVXS_LEVELS: Final = {
    "CRIT": logging.CRITICAL,
    "ERR": logging.ERROR,
    "WARN": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


ArgValue: TypeAlias = str | int | float | bool | None | list[str | int | float]
"""A value of one option in an `args` mapping."""


def command_line(args: Sequence[str] | Mapping[str, ArgValue]) -> list[str]:
    """Return *args* as the arguments following the module.

    A list is kept in order, each item as text. A mapping gives `--key value` for each entry:
    `True` gives `--key` alone, `False` and `None` give nothing, and a list
    gives `--key` followed by each item. Keys are used as written.

    Raises
    ------
    TypeError
        If *args* is text rather than a list or a mapping.
    """
    if isinstance(args, str):
        raise TypeError(f"args must be a list or a mapping, not the text {args!r}")
    if not isinstance(args, Mapping):
        return [str(arg) for arg in args]
    line: list[str] = []
    for key, value in args.items():
        if value is None or value is False:
            continue
        line.append(f"--{key}")
        if value is True:
            continue
        if isinstance(value, list):
            line.extend(str(item) for item in value)
        else:
            line.append(str(value))
    return line


class Service:
    """A server devices talk to, and its process if the session owns it.

    A container makes one per declared service. A service with a *module* is
    launched as `python -m <module> <args>`; one without is attached to, runs
    elsewhere, and `start` and `stop` do nothing. Each output line is logged
    under `redsun.service.<name>`: as the record it describes if it is a JSON
    log record, at `DEBUG` otherwise; see `service_record`.

    Parameters
    ----------
    name
        Name of the service.
    prefix
        Prefix given to each device naming the service.
    module
        Module to run. `None` attaches to a service that is already running.
    args
        Arguments following the module: a list, or a mapping of option names
        to values, which `--` is put before.
    ready
        Text of the output line marking the service ready. `None` counts it
        ready once its process starts.
    stop_timeout
        Seconds each step of `stop` waits for the process to exit.
    transport
        Protocol the service is reached over: `channel-access` or `pv-access`.
        The session settles it for every service it holds.
    address
        Where an attached service answers, added to this process's address
        list when it starts. `None` keeps the list as the environment gives
        it.

    Raises
    ------
    TypeError
        If *args* are given without a *module*, or as text, or an *address*
        with a *module*.
    ValueError
        If *transport* is not a protocol a session accepts.
    """

    __slots__ = (
        "__weakref__",
        "_drain",
        "_is_ready",
        "_process",
        "_settled",
        "_stopping",
        "_tail",
        "address",
        "args",
        "module",
        "name",
        "prefix",
        "ready",
        "stop_timeout",
        "transport",
    )

    sig_exited = Signal(str, int)
    """Emitted with the name and exit code when a ready service exits unasked."""

    def __init__(
        self,
        name: str,
        prefix: str = "",
        module: str | None = None,
        args: Sequence[str] | Mapping[str, ArgValue] = (),
        ready: str | None = None,
        stop_timeout: float = STOP_TIMEOUT,
        transport: str = CHANNEL_ACCESS,
        address: str | None = None,
    ) -> None:
        if args and module is None:
            raise TypeError(
                f"service {name!r} gives args but no module to run; an attached "
                "service only lends its prefix"
            )
        if address is not None and module is not None:
            raise TypeError(
                f"service {name!r} gives an address and a module; a launched "
                "service's address is the session's to choose"
            )
        if transport not in TRANSPORTS:
            known = ", ".join(map(repr, sorted(TRANSPORTS)))
            raise ValueError(
                f"service {name!r} names transport {transport!r}; expected one of {known}"
            )
        self.name = name
        self.prefix = prefix
        self.address = address
        self.module = module
        self.args = command_line(args)
        self.ready = ready
        self.stop_timeout = stop_timeout
        self.transport = transport
        self._tail: deque[str] = deque(maxlen=TAIL_LINES)
        self._process: subprocess.Popen[str] | None = None
        self._drain: threading.Thread | None = None
        # set once the readiness line appears or the output ends, whichever is
        # first, so that a process dying at startup does not wait out the timeout
        self._settled = threading.Event()
        self._is_ready = False
        self._stopping = False

    @property
    def launched(self) -> bool:
        """Whether the session launches this service rather than attaching to it."""
        return self.module is not None

    @property
    def running(self) -> bool:
        """Whether the process this service launched is still running."""
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Launch the service and wait until it prints its readiness line.

        The process runs without a console window on Windows, and its
        transport gives it the environment it is reached on and tells this
        process where to look, so devices find it among several local
        services. What a transport reserves lasts for every start in this
        process. The process learns its name, prefix, ready text and the
        level this session records at through the functions of
        `redsun.services`, so a module serving several sessions needs no
        arguments for them. The process
        writes UTF-8, and each output line is logged as `service_record`
        rebuilds it. An attached service only adds its address to this
        process's list, if it names one.

        Raises
        ------
        TimeoutError
            If the readiness line does not appear within `STARTUP_TIMEOUT`; the
            process is stopped and its last output logged.
        RuntimeError
            If the process exits before it is ready.
        """
        if self.module is None:
            if self.address is not None:
                TRANSPORTS[self.transport].attach(self.address)
            return
        if self.running:
            return
        transport = TRANSPORTS[self.transport]
        with launch_lock:
            reserved = transport.reserve(self.name)
            transport.publish(self.name)
            env = {
                **os.environ,
                **reserved,
                "PYTHONUTF8": "1",
                NAME_VARIABLE: self.name,
                PREFIX_VARIABLE: self.prefix,
                # the number, not the name: a level without a standard name
                # would be unknown to the service's own logging
                LEVEL_VARIABLE: str(logger.getEffectiveLevel()),
            }
            if self.ready is None:
                env.pop(READY_VARIABLE, None)
            else:
                env[READY_VARIABLE] = self.ready
        flags = 0
        # an if statement, not an expression: only the statement narrows the
        # platform for a type checker running on another one
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW
        self._tail.clear()
        self._settled.clear()
        self._is_ready = self.ready is None
        self._stopping = False
        self._process = subprocess.Popen(
            [sys.executable, "-m", self.module, *self.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
        self._drain = threading.Thread(
            target=self._drain_output,
            args=(self._process,),
            name=f"service-{self.name}",
            daemon=True,
        )
        self._drain.start()

        if not self._is_ready:
            self._settled.wait(STARTUP_TIMEOUT)
        if self._is_ready:
            logger.info("Service '%s' started", self.name)
            return
        code = self._process.wait() if self._settled.is_set() else None
        self.stop()
        reason = (
            f"not ready after {STARTUP_TIMEOUT:g} s"
            if code is None
            else f"exited with code {code} before it was ready"
        )
        logger.error(self._with_tail(f"Service '{self.name}' {reason}"))
        raise (TimeoutError if code is None else RuntimeError)(reason)

    def stop(self) -> None:
        """Stop the launched process, escalating until it exits.

        First its standard input is closed, the one request that lets a service
        clean up on every platform. On POSIX a service still running after
        `stop_timeout` gets `SIGINT`; one still running after that, or after
        the first step on Windows, is killed.
        """
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            self._stopping = True
            if process.stdin is not None:
                process.stdin.close()
            stopped = exited(process, self.stop_timeout)
            if not stopped and sys.platform != "win32":
                process.send_signal(signal.SIGINT)
                stopped = exited(process, self.stop_timeout)
            if not stopped:
                logger.warning(
                    "Service '%s' did not stop within %g s, killing it",
                    self.name,
                    self.stop_timeout,
                )
                process.kill()
                process.wait()
            logger.info(
                "Service '%s' stopped with exit code %s", self.name, process.returncode
            )
        self._join_drain()
        self._process = None

    def _drain_output(self, process: subprocess.Popen[str]) -> None:
        """Log the service's output until it ends, then report an unexpected exit."""
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.rstrip()
            self._tail.append(line)
            record = service_record(self.name, line)
            target = logging.getLogger(record.name)
            if target.isEnabledFor(record.levelno):
                target.handle(record)
            if not self._is_ready and self.ready is not None and self.ready in line:
                self._is_ready = True
                self._settled.set()
        self._settled.set()
        code = process.wait()
        if self._stopping or not self._is_ready:
            return
        logger.error(self._with_tail(f"Service '{self.name}' exited with code {code}"))
        self.sig_exited.emit(self.name, code)

    def _join_drain(self) -> None:
        """Wait for the output thread to log what the process printed last."""
        if self._drain is not None and self._drain is not threading.current_thread():
            self._drain.join(timeout=5)

    def _with_tail(self, message: str) -> str:
        """Return *message* followed by the service's latest output."""
        if not self._tail:
            return message
        return f"{message}; last output:\n" + "\n".join(self._tail)


def service_record(service: str, line: str) -> logging.LogRecord:
    """Rebuild the log record one line of *service*'s output describes.

    Two JSON layouts are read: `loguru`'s with `serialize=True`, and an
    object with a `logging.LogRecord`'s `name`, `levelno`, `created`,
    `msg` and `exc_text`. Such a record keeps its level, time and traceback,
    under `redsun.service.<service>.<its logger>`. A line `pvxs` writes,
    `<time> <LEVEL> <logger> <message>`, keeps its level, time and logger
    the same way. Any other line, such as a `print`, becomes a `DEBUG`
    record under `redsun.service.<service>`.
    """
    base = f"{SERVICE_LOGGER}.{service}"
    fields: dict[str, Any] = {
        "name": base,
        "levelno": logging.DEBUG,
        "levelname": "DEBUG",
        "msg": line,
        "clsname": service,
    }
    pvxs = PVXS_LINE.match(line)
    if pvxs is not None:
        # pvxs writes nanoseconds; fromisoformat reads at most microseconds
        stamp = datetime.fromisoformat(f"{pvxs['time']}.{pvxs['fraction'][:6]}")
        fields.update(
            name=f"{base}.{pvxs['name']}",
            levelno=PVXS_LEVELS[pvxs["level"]],
            levelname=logging.getLevelName(PVXS_LEVELS[pvxs["level"]]),
            msg=pvxs["message"],
            created=stamp.timestamp(),
            uid=pvxs["name"],
        )
        return logging.makeLogRecord(fields)
    # a JSON record is an object; any other line would only fail to parse
    if not line.startswith("{"):
        return logging.makeLogRecord(fields)
    try:
        data = json.loads(line)
        if "record" in data:
            loguru = data["record"]
            source = loguru["extra"].get("logger_name") or loguru["name"]
            fields.update(
                name=f"{base}.{source}",
                levelno=loguru["level"]["no"],
                levelname=loguru["level"]["name"],
                msg=loguru["message"],
                created=loguru["time"]["timestamp"],
                exc_text=(
                    data["text"].split("\n", 1)[1].strip()
                    if loguru["exception"]
                    else None
                ),
                uid=source,
            )
        else:
            fields.update(
                name=f"{base}.{data['name']}",
                levelno=data["levelno"],
                levelname=logging.getLevelName(data["levelno"]),
                msg=data["msg"],
                created=data["created"],
                exc_text=data.get("exc_text"),
                uid=data["name"],
            )
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        pass
    return logging.makeLogRecord(fields)


def exited(process: subprocess.Popen[str], timeout: float) -> bool:
    """Return whether *process* exits within *timeout* seconds."""
    try:
        process.wait(timeout)
    except subprocess.TimeoutExpired:
        return False
    return True
