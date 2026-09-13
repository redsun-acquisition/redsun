"""Servers a session's devices talk to, and the processes behind them.

A container declares services with
[`declare_service`][redsun.containers.declare_service] and makes a `Service` for
each. A launched service is a child process the container starts and stops; an
attached one already runs elsewhere and only lends its devices their prefix.
"""

from __future__ import annotations

from ._service import STARTUP_TIMEOUT, STOP_TIMEOUT, Service

__all__ = ["STARTUP_TIMEOUT", "STOP_TIMEOUT", "Service"]
