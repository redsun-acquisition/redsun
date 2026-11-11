"""Run the calls a process pool sends until it closes the pipe."""

from __future__ import annotations

import faulthandler
import logging
import os
import sys
import threading
import traceback
from multiprocessing.connection import Client

from redsun.services import configure_logging, ready
from redsun.workers import ADDRESS_VARIABLE, AUTHKEY_VARIABLE

from ..compute._channel import Channel
from ..compute._pickling import name_of

QT_MODULES = ("qtpy", "PyQt6", "PySide6")

logger = logging.getLogger("redsun")


def main() -> None:
    """Connect to the pool, say the worker is ready, and answer every call it sends."""
    configure_logging()
    faulthandler.enable()
    channel = Channel(
        Client(
            os.environ[ADDRESS_VARIABLE],
            authkey=bytes.fromhex(os.environ[AUTHKEY_VARIABLE]),
        )
    )
    threading.Thread(target=exit_when_stdin_closes, daemon=True).start()
    ready()
    try:
        while True:
            before = loaded_qt()
            try:
                kind, id, payload = channel.receive()
            except EOFError:
                break
            if kind != "call":
                continue
            fn, args, kwargs = payload
            name = name_of(fn)
            if loaded := loaded_qt() - before:
                logger.warning(
                    "%s imported %s into a worker process; keep it in a module without Qt",
                    name,
                    ", ".join(sorted(loaded)),
                )
            try:
                result = fn(*args, **kwargs)
            except Exception as error:  # noqa: BLE001 - every error goes back to the caller
                answer_error(channel, id, error)
                continue
            try:
                channel.send("result", id, result)
            except (EOFError, OSError):
                raise
            except Exception as error:  # noqa: BLE001 - whatever pickling raised
                channel.send(
                    "error",
                    id,
                    TypeError(
                        f"{name}() returned a value that cannot be pickled: {error}"
                    ),
                )
    finally:
        channel.close()


def loaded_qt() -> set[str]:
    """Return the Qt modules this process has imported."""
    return {module for module in QT_MODULES if module in sys.modules}


def answer_error(channel: Channel, id: int, error: Exception) -> None:
    """Send *error* with its traceback as a note, or a `RuntimeError` naming it if it cannot be pickled."""
    note = "Traceback in the worker process (most recent call last):\n" + "".join(
        traceback.format_tb(error.__traceback__)
    )
    error.add_note(note)
    try:
        channel.send("error", id, error)
    except (EOFError, OSError):
        raise
    except Exception:  # noqa: BLE001 - whatever pickling raised
        stand_in = RuntimeError(f"{type(error).__name__}: {error}")
        stand_in.add_note(note)
        channel.send("error", id, stand_in)


def exit_when_stdin_closes() -> None:
    """End the process once the pool closes standard input."""
    sys.stdin.read()
    os._exit(0)


if __name__ == "__main__":
    main()
