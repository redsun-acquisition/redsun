from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import threading
from dataclasses import dataclass
from typing import Final

from redsun.log import DEFAULT_LEVEL, logger

from ._transports import LOOPBACK

NAME_VARIABLE: Final = "REDSUN_SERVICE_NAME"
"""Variable holding the name a session declares a launched service under."""

PREFIX_VARIABLE: Final = "REDSUN_SERVICE_PREFIX"
"""Variable holding the prefix of the declaration, empty when it gives none."""

READY_VARIABLE: Final = "REDSUN_SERVICE_READY"
"""Variable holding the text the session waits for, set only when declared."""

LEVEL_VARIABLE: Final = "REDSUN_LOG_LEVEL"
"""Variable holding the number of the level the session records at."""

ATTEMPT_TIMEOUT: Final = 1.0
"""Seconds `ready_when_reachable` waits for each answer, and between failures."""


@dataclass(frozen=True)
class ServiceIdentity:
    """What a session tells a service process it launched."""

    name: str
    """Name the session declares the service under."""

    prefix: str
    """Prefix given to each device naming the service; empty when none."""


class JsonLines(logging.Formatter):
    """Format a record as the JSON object a session rebuilds into a record."""

    def format(self, record: logging.LogRecord) -> str:
        """Return *record* as one line of JSON."""
        return json.dumps(
            {
                "name": record.name,
                "levelno": record.levelno,
                "created": record.created,
                "msg": record.getMessage(),
                "exc_text": (
                    self.formatException(record.exc_info) if record.exc_info else None
                ),
            }
        )


def configure_logging() -> None:
    """Log at the session's level, in lines the session rebuilds into records.

    Records of `logging` and, when it is installed, of `loguru` go to
    standard output as JSON, each keeping its level, time, logger name and
    traceback. The level is the one the session records at, `INFO` when no
    session launched the process. The handlers already on the root logger, the
    `redsun` logger and `loguru` are replaced, so none of their records is
    written twice.
    """
    level = level_from_environment()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLines())
    logging.basicConfig(level=level, handlers=[handler], force=True)
    # importing redsun gives its logger a plain stdout handler, which would
    # write each of its records a second time, as text
    for installed in list(logger.handlers):
        logger.removeHandler(installed)
    logger.setLevel(level)
    try:
        from loguru import logger as loguru_logger  # noqa: PLC0415
    except ImportError:
        return
    loguru_logger.remove()
    loguru_logger.add(sys.stdout, serialize=True, level=level)


def level_from_environment() -> int:
    """Return the level the session records at, `INFO` when none is known.

    The variable holds a number; a level name, in any case, is read too.
    """
    value = os.environ.get(LEVEL_VARIABLE, "")
    if value.isdigit():
        return int(value)
    known = logging.getLevelNamesMapping()
    return known.get(value.upper(), known[DEFAULT_LEVEL])


def identity() -> ServiceIdentity | None:
    """Return the name and prefix the session gave this process.

    `None` when no session launched it, so a service run on its own falls back
    on defaults of its own.
    """
    name = os.environ.get(NAME_VARIABLE)
    if name is None:
        return None
    return ServiceIdentity(name, os.environ.get(PREFIX_VARIABLE, ""))


def ready() -> None:
    """Print the text the session waits for before it counts this service ready.

    The text is the one the service's declaration gives. Without one, nothing
    is printed: the session does not wait then.
    """
    text = os.environ.get(READY_VARIABLE)
    if text is not None:
        print(text, flush=True)


async def ready_when_reachable(pv: str) -> None:
    """Call [`ready`][redsun.services.ready] once *pv* answers over PVAccess.

    For a server that prints no line of its own once it serves. *pv* is
    looked for on the loopback, where a launched service listens; it needs
    `p4p`, which a service serving PVAccess already has. A failed attempt
    other than a timeout is logged as a warning and retried.
    """
    from p4p.client.asyncio import Context  # noqa: PLC0415

    with Context("pva", conf={"EPICS_PVA_ADDR_LIST": LOOPBACK}) as client:
        while True:
            try:
                await asyncio.wait_for(client.get(pv), timeout=ATTEMPT_TIMEOUT)
            except TimeoutError:
                continue
            except Exception as error:  # noqa: BLE001  # pragma: no cover
                # the session waits for the ready line, so a failure here
                # would otherwise show only as its startup timeout
                logger.warning("%s did not answer, retrying: %s", pv, error)
                await asyncio.sleep(ATTEMPT_TIMEOUT)
                continue
            break
    ready()


async def wait_for_stop() -> None:
    """Return once the session asks this service to stop.

    The session asks by closing standard input, which a daemon thread watches,
    so a service ending for another reason is not held up by it. When no
    session launched the process, this waits until cancelled and watches
    nothing: standard input may be closed from the start there.
    """
    stopped: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    if identity() is not None:
        threading.Thread(
            target=settle_when_stdin_closes, args=(stopped,), daemon=True
        ).start()
    await stopped


def stop_on_request() -> None:
    """Raise `SIGINT` in this process once the session asks it to stop.

    For a server whose `run` blocks: it shuts down as it would on Ctrl+C.
    Does nothing when no session launched the process.
    """
    if identity() is not None:
        threading.Thread(target=interrupt_when_stdin_closes, daemon=True).start()


def settle_when_stdin_closes(stopped: asyncio.Future[None]) -> None:
    """Set *stopped*'s result on its loop once standard input closes."""
    sys.stdin.read()
    try:
        stopped.get_loop().call_soon_threadsafe(settle, stopped)
    except RuntimeError:  # pragma: no cover
        # the loop already closed: nobody waits any more
        pass


def settle(stopped: asyncio.Future[None]) -> None:
    """Set *stopped*'s result unless it is already done or cancelled."""
    if not stopped.done():
        stopped.set_result(None)


def interrupt_when_stdin_closes() -> None:
    """Send `SIGINT` to the main thread of this process once standard input closes."""
    sys.stdin.read()
    main = threading.main_thread().ident
    if hasattr(signal, "pthread_kill") and main is not None:
        # on POSIX a signal raised here reaches this thread only, and a main
        # thread blocked in a system call such as select would not wake for it
        signal.pthread_kill(main, signal.SIGINT)
    else:
        signal.raise_signal(signal.SIGINT)
