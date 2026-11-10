"""Limits on the native threads a session's libraries start."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, final

from threadpoolctl import threadpool_limits

if TYPE_CHECKING:
    from collections.abc import Callable


@final
class Limits:
    """Native thread limits, applied once and restored at shutdown."""

    def __init__(self, switch_interval_ms: float | None = None) -> None:
        self._switch_interval = (
            None if switch_interval_ms is None else switch_interval_ms / 1000
        )
        self._applied = False
        self._pools: threadpool_limits | None = None
        self._torch_threads: int | None = None
        self._found_interval: float | None = None

    def apply(self, native_threads: int) -> None:
        """Limit the native thread pools of the loaded libraries, on the first call only.

        Call it from the main thread.
        """
        if self._applied:
            return
        self._applied = True
        self._pools = threadpool_limits(limits=native_threads)
        if (torch := sys.modules.get("torch")) is not None:
            self._torch_threads = torch.get_num_threads()
            torch.set_num_threads(native_threads)
        if self._switch_interval is not None:
            self._found_interval = sys.getswitchinterval()
            sys.setswitchinterval(self._switch_interval)

    def restore(self) -> None:
        """Put back what `apply` changed; a second call does nothing."""
        if self._pools is not None:
            self._pools.restore_original_limits()
            self._pools = None
        if self._torch_threads is not None:
            sys.modules["torch"].set_num_threads(self._torch_threads)
            self._torch_threads = None
        if self._found_interval is not None:
            sys.setswitchinterval(self._found_interval)
            self._found_interval = None

    def initializer(self, native_threads: int) -> Callable[[], None]:
        """Return what each pool thread runs to apply the limit in itself."""

        def limit_native_threads() -> None:
            threadpool_limits(limits=native_threads)

        return limit_native_threads
