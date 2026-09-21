from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
from collections import deque
from typing import TYPE_CHECKING, Final

from psygnal import Signal

from redsun.log import SERVICE_LOGGER

from ._transports import CHANNEL_ACCESS, TRANSPORTS

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

logger = logging.getLogger("redsun")

STARTUP_TIMEOUT: Final = 15.0
"""Seconds a launched service has to print its readiness line."""

STOP_TIMEOUT: Final = 10.0
"""Seconds each step of `Service.stop` waits, unless the service gives its own."""

TAIL_LINES: Final = 20
"""Lines of a service's latest output kept to explain an unexpected exit."""


class Service:
    """A server devices talk to, and its process if the session owns it.

    A container makes one per declared service. A service with a *module* is
    launched as ``python -m <module> <args>``; one without is attached to, runs
    elsewhere, and `start` and `stop` do nothing. Each output line is logged
    under ``redsun.service.<name>``: as the record it describes if it is a JSON
    log record, at ``DEBUG`` otherwise; see `service_record`.

    Parameters
    ----------
    name : str
        Name of the service.
    prefix : str
        Prefix given to each device naming the service.
    module : str | None
        Module to run. ``None`` attaches to a service that is already running.
    args : Sequence[str]
        Command-line arguments following the module.
    ready : str | None
        Text of the output line marking the service ready. ``None`` counts it
        ready once its process starts.
    stop_timeout : float
        Seconds each step of `stop` waits for the process to exit.
    transport : str
        Protocol the service is reached over, as `redsun.services._transports`
        names them. The session settles it for every service it holds.

    Raises
    ------
    TypeError
        If *args* are given without a *module*.
    """

    __slots__ = (
        "__weakref__",
        "_drain",
        "_is_ready",
        "_process",
        "_settled",
        "_stopping",
        "_tail",
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
        args: Sequence[str] = (),
        ready: str | None = None,
        stop_timeout: float = STOP_TIMEOUT,
        transport: str = CHANNEL_ACCESS,
    ) -> None:
        if args and module is None:
            raise TypeError(
                f"service {name!r} gives args but no module to run; an attached "
                "service only lends its prefix"
            )
        self.name = name
        self.prefix = prefix
        self.module = module
        self.args = list(args)
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
        process. It also reads ``REDSUN_SERVICE_NAME`` and
        ``REDSUN_SERVICE_PREFIX`` from its environment, so a module serving
        several sessions needs no arguments to name its channels. The process
        writes UTF-8, and each output line is logged as `service_record`
        rebuilds it.

        Raises
        ------
        TimeoutError
            If the readiness line does not appear within `STARTUP_TIMEOUT`; the
            process is stopped and its last output logged.
        RuntimeError
            If the process exits before it is ready.
        """
        if self.module is None or self.running:
            return
        transport = TRANSPORTS[self.transport]
        reserved = transport.reserve(self.name)
        transport.publish(self.name)
        env = {
            **os.environ,
            **reserved,
            "PYTHONUTF8": "1",
            "REDSUN_SERVICE_NAME": self.name,
            "REDSUN_SERVICE_PREFIX": self.prefix,
        }
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
        `stop_timeout` gets ``SIGINT``; one still running after that, or after
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

    Two JSON layouts are read: ``loguru``'s with ``serialize=True``, and an
    object with a `logging.LogRecord`'s ``name``, ``levelno``, ``created``,
    ``msg`` and ``exc_text``. Such a record keeps its level, time and traceback,
    under ``redsun.service.<service>.<its logger>``. Any other line, such as a
    ``print``, becomes a ``DEBUG`` record under ``redsun.service.<service>``.
    """
    base = f"{SERVICE_LOGGER}.{service}"
    fields: dict[str, Any] = {
        "name": base,
        "levelno": logging.DEBUG,
        "levelname": "DEBUG",
        "msg": line,
        "clsname": service,
    }
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
