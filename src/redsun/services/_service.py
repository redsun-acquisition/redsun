from __future__ import annotations

import logging
import os
import signal
import socket
import subprocess
import sys
import threading
from collections import deque
from typing import TYPE_CHECKING, Final

from psygnal import Signal

if TYPE_CHECKING:
    from collections.abc import Sequence

STARTUP_TIMEOUT: Final = 15.0
"""Seconds a launched service has to print its readiness line."""

TAIL_LINES: Final = 20
"""Lines of a service's latest output kept to explain an unexpected exit."""


class Service:
    """A server some devices talk to, and the process behind it if the session owns one.

    A container makes one for each service it declares. A service with a
    *module* is launched as ``python -m <module> <args>``; one without is
    attached to, already running elsewhere, and `start` and `stop` do nothing.
    Its output is logged under ``redsun.service.<name>``.

    Parameters
    ----------
    name : str
        Name of the service.
    prefix : str
        Prefix given to every device naming the service.
    module : str | None
        Module to run. ``None`` attaches to a service that is already running.
    args : Sequence[str]
        Command-line arguments following the module.
    ready : str | None
        Text of the output line that marks the service ready. ``None`` counts
        it ready as soon as its process starts.
    stop_timeout : float
        Seconds each step of `stop` waits for the process to exit.

    Raises
    ------
    TypeError
        If *args* are given without a *module*.
    """

    __slots__ = (
        "__weakref__",
        "_drain",
        "_is_ready",
        "_log",
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
        stop_timeout: float = 10.0,
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
        self._log = logging.getLogger(f"redsun.service.{name}")
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

        The process runs without a console window on Windows, with its own
        Channel Access server port, which is added to ``EPICS_CA_ADDR_LIST`` in
        this process so that a device reaches it among several local services.
        Its output is logged line by line at ``DEBUG``.

        Raises
        ------
        TimeoutError
            If the readiness line does not appear within `STARTUP_TIMEOUT`. The
            process is stopped and its latest output logged.
        RuntimeError
            If the process exits before it is ready.
        """
        if self.module is None or self.running:
            return
        port = free_udp_port()
        env = {**os.environ, "EPICS_CA_SERVER_PORT": str(port), "PYTHONUTF8": "1"}
        os.environ["EPICS_CA_ADDR_LIST"] = " ".join(
            filter(None, [os.environ.get("EPICS_CA_ADDR_LIST"), f"127.0.0.1:{port}"])
        )
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
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

        if self._is_ready or self._settled.wait(STARTUP_TIMEOUT) and self._is_ready:
            self._log.info("Service '%s' started", self.name)
            return
        if self._settled.is_set():
            code = self._process.wait()
            self._join_drain()
            self._process = None
            self._log.error(
                self._with_tail(f"Service '{self.name}' exited with code {code}")
            )
            raise RuntimeError(f"exited with code {code} before it was ready")
        self.stop()
        self._log.error(
            self._with_tail(
                f"Service '{self.name}' not ready after {STARTUP_TIMEOUT:g} s"
            )
        )
        raise TimeoutError(f"not ready after {STARTUP_TIMEOUT:g} s")

    def stop(self) -> None:
        """Stop the process this service launched, escalating until it exits.

        Closing the process's standard input is asked first, the one request
        that lets a service clean up on every platform. On POSIX a service
        still running after `stop_timeout` is sent ``SIGINT``; one still
        running after that, or after the first step on Windows, is killed.
        """
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            self._stopping = True
            if process.stdin is not None:
                process.stdin.close()
            if not exited(process, self.stop_timeout):
                if sys.platform != "win32":
                    process.send_signal(signal.SIGINT)
                if not exited(process, self.stop_timeout):
                    self._log.warning(
                        "Service '%s' did not stop within %g s, killing it",
                        self.name,
                        self.stop_timeout,
                    )
                    process.kill()
                    process.wait()
            self._log.info(
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
            self._log.debug(line)
            if not self._is_ready and self.ready is not None and self.ready in line:
                self._is_ready = True
                self._settled.set()
        self._settled.set()
        code = process.wait()
        if self._stopping or not self._is_ready:
            return
        self._log.error(
            self._with_tail(f"Service '{self.name}' exited with code {code}")
        )
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


def exited(process: subprocess.Popen[str], timeout: float) -> bool:
    """Return whether *process* exits within *timeout* seconds."""
    try:
        process.wait(timeout)
    except subprocess.TimeoutExpired:
        return False
    return True


def free_udp_port() -> int:
    """Return a UDP port on the loopback interface that nothing is bound to."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port
