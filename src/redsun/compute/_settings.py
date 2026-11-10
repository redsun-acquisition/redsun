"""The cores pools are sized from, how presets split them, and native thread limits."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypedDict, final

from threadpoolctl import threadpool_limits

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

Preset = Literal["latency", "balanced", "throughput"]
"""How the compute cores are split between pool threads and native threads."""

RELATION_PROCESSOR_CORE = 0
INSUFFICIENT_BUFFER = 122

logger = logging.getLogger("redsun.compute")


class ComputeSettings(TypedDict, total=False):
    """The `compute` section a session class declares, key by key."""

    preset: Preset
    """How the compute cores are split between threads and native libraries."""

    cores: int
    """Cap on the compute cores; default: the physical cores less `reserve`."""

    reserve: list[int]
    """Cores kept for the window's thread; default: one physical core."""

    switch_interval_ms: float | None
    """Interpreter thread switch interval in milliseconds; `None` leaves it alone."""


@dataclass(frozen=True, slots=True)
class ThreadPoolSettings:
    """How many threads a thread pool has."""

    threads: int
    """Worker threads; 0 runs each call in the thread that submits it."""

    native_threads: int
    """Threads each worker's native libraries may use."""


def physical_cores() -> int:
    """Return the number of physical cores, not logical CPUs.

    Falls back to `os.cpu_count()` and logs a warning where the count cannot
    be read.
    """
    # One function, so no reader can be imported and used on its own.
    try:
        if sys.platform == "win32":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            needed = ctypes.c_ulong(0)
            kernel32.GetLogicalProcessorInformationEx(
                RELATION_PROCESSOR_CORE, None, ctypes.byref(needed)
            )
            if ctypes.get_last_error() != INSUFFICIENT_BUFFER:
                raise ctypes.WinError(ctypes.get_last_error())
            buffer = ctypes.create_string_buffer(needed.value)
            if not kernel32.GetLogicalProcessorInformationEx(
                RELATION_PROCESSOR_CORE, buffer, ctypes.byref(needed)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            count = offset = 0
            while offset < needed.value:
                size = int.from_bytes(buffer.raw[offset + 4 : offset + 8], "little")
                if size == 0:
                    raise ValueError("a processor record has no size")
                count += 1
                offset += size
        elif sys.platform == "darwin":
            value = ctypes.c_int(0)
            size = ctypes.c_size_t(ctypes.sizeof(value))
            libc = ctypes.CDLL(None)
            libc.sysctlbyname.argtypes = [
                ctypes.c_char_p,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_size_t),
                ctypes.c_void_p,
                ctypes.c_size_t,
            ]
            libc.sysctlbyname.restype = ctypes.c_int
            if libc.sysctlbyname(
                b"hw.physicalcpu", ctypes.byref(value), ctypes.byref(size), None, 0
            ):
                raise OSError("sysctlbyname hw.physicalcpu failed")
            count = value.value
        elif sys.platform.startswith("linux"):
            siblings = set()
            for topology in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/topology"):
                for name in ("core_cpus_list", "thread_siblings_list"):
                    if (path := topology / name).exists():
                        siblings.add(path.read_text().strip())
                        break
            count = len(siblings)
        else:
            raise OSError(f"no reader for {sys.platform}")
        if count < 1:
            raise OSError("no physical core found")
    except (OSError, ValueError, AttributeError) as error:
        logger.warning(
            f"Could not read the physical cores ({error}); using the logical CPUs"
        )
        return os.cpu_count() or 1
    return count


def compute_cores(
    physical: int, *, cap: int | None, reserve: Sequence[int] | None
) -> int:
    """Return the cores the shared pools may use, at least 1.

    One core stays free unless *reserve* lists the cores kept for the window's thread, and
    *cap* limits the result.
    """
    cores = physical - (len(reserve) if reserve is not None else 1)
    if cap is not None:
        cores = min(cores, cap)
    return max(cores, 1)


def split(preset: Preset, cores: int) -> ThreadPoolSettings:
    """Split *cores* between pool threads and native threads as *preset* says."""
    match preset:
        case "latency":
            return ThreadPoolSettings(1, cores)
        case "balanced":
            threads = max(2, cores // 4)
            return ThreadPoolSettings(threads, max(cores // threads, 1))
        case "throughput":
            return ThreadPoolSettings(cores, 1)


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

    @staticmethod
    def initializer(native_threads: int) -> Callable[[], object]:
        """Return what each pool thread runs to apply the limit in itself."""
        return partial(threadpool_limits, limits=native_threads)
