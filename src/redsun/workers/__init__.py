"""The worker process a process pool starts, run as `python -m redsun.workers`.

The worker connects to the pool's listener, runs each call the pool sends,
and answers with its result or its error, until the pool closes the pipe or
standard input.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ADDRESS_VARIABLE", "AUTHKEY_VARIABLE"]

ADDRESS_VARIABLE: Final = "REDSUN_WORKER_ADDRESS"
"""Variable holding the address of the pool's listener."""

AUTHKEY_VARIABLE: Final = "REDSUN_WORKER_AUTHKEY"
"""Variable holding the key the worker connects with, in hexadecimal."""
