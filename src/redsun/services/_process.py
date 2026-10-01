from __future__ import annotations

import asyncio
import os
import signal
import sys
import threading
from dataclasses import dataclass
from typing import Final

NAME_VARIABLE: Final = "REDSUN_SERVICE_NAME"
"""Variable holding the name a session declares a launched service under."""

PREFIX_VARIABLE: Final = "REDSUN_SERVICE_PREFIX"
"""Variable holding the prefix of the declaration, empty when it gives none."""

READY_VARIABLE: Final = "REDSUN_SERVICE_READY"
"""Variable holding the text the session waits for, set only when declared."""

LEVEL_VARIABLE: Final = "REDSUN_LOG_LEVEL"
"""Variable holding the name of the level the session records at."""


@dataclass(frozen=True)
class ServiceIdentity:
    """What a session tells a service process it launched."""

    name: str
    """Name the session declares the service under."""

    prefix: str
    """Prefix given to each device naming the service; empty when none."""


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
    except RuntimeError:
        # the loop already closed: nobody waits any more
        pass


def settle(stopped: asyncio.Future[None]) -> None:
    """Set *stopped*'s result unless it is already done or cancelled."""
    if not stopped.done():
        stopped.set_result(None)


def interrupt_when_stdin_closes() -> None:
    """Raise `SIGINT` in this process once standard input closes."""
    sys.stdin.read()
    signal.raise_signal(signal.SIGINT)
