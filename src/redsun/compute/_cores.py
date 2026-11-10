"""The cores pools are sized from, and how presets split them."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from ._future import logger
from ._threads import ThreadPoolSettings

if TYPE_CHECKING:
    from collections.abc import Sequence

Preset = Literal["latency", "balanced", "throughput"]
"""How the compute cores are split between pool threads and native threads."""

RELATION_PROCESSOR_CORE = 0
INSUFFICIENT_BUFFER = 122


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
            return ThreadPoolSettings(1, max(cores, 1))
        case "balanced":
            threads = max(2, cores // 4)
            return ThreadPoolSettings(threads, max(cores // threads, 1))
        case "throughput":
            return ThreadPoolSettings(max(cores, 1), 1)
