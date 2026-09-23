"""Servers a session's devices talk to, and the processes behind them.

A session declares services with `AsService` and makes a `Service` for
each. A launched service is a child process the session starts and stops; an
attached one already runs elsewhere and only lends its devices their prefix.
"""

from __future__ import annotations

from ._service import STARTUP_TIMEOUT, STOP_TIMEOUT, Service

__all__ = ["STARTUP_TIMEOUT", "STOP_TIMEOUT", "Service"]
