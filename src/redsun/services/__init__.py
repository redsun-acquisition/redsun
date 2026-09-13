"""Servers the devices of a session talk to, and the processes behind them.

A container declares its services with
[`declare_service`][redsun.containers.declare_service] and makes a `Service` for
each: launched, as a child process the container starts and stops, or attached
to, already running elsewhere and lending only the prefix its devices address it
by.
"""

from __future__ import annotations

from ._service import STARTUP_TIMEOUT, Service

__all__ = ["STARTUP_TIMEOUT", "Service"]
