from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Preset = Literal["latency", "balanced", "throughput"]

RELATION_PROCESSOR_CORE = 0

logger = logging.getLogger("redsun")


class Header(ctypes.Structure):
    """Start of each record `GetLogicalProcessorInformationEx` returns."""

    _fields_ = [("Relationship", ctypes.c_int), ("Size", wt.DWORD)]


@dataclass(frozen=True)
class Budget:
    """How many cores computation may use and how it spends them."""

    cores: int
    """Cores the budget covers."""

    threads: int
    """Worker threads in the pool."""

    native_threads: int
    """Threads each worker's native libraries may use."""


def windows_cores() -> int:
    """Count physical cores across all processor groups."""
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        size = wt.DWORD(0)
        kernel32.GetLogicalProcessorInformationEx(
            RELATION_PROCESSOR_CORE, None, ctypes.byref(size)
        )
        buffer = ctypes.create_string_buffer(size.value)
        if not kernel32.GetLogicalProcessorInformationEx(
            RELATION_PROCESSOR_CORE, buffer, ctypes.byref(size)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        count, offset = 0, 0
        while offset < size.value:
            count += 1
            offset += Header.from_buffer(buffer, offset).Size
        return count
    raise OSError("not Windows")


def linux_cores() -> int:
    """Count distinct (package, core) pairs under sysfs."""
    pairs = set()
    for topology in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/topology"):
        package = (topology / "physical_package_id").read_text().strip()
        core = (topology / "core_id").read_text().strip()
        pairs.add((package, core))
    if not pairs:
        raise OSError("no cpu topology in sysfs")
    return len(pairs)


def physical_cores() -> int:
    """Return the number of physical cores, at most the logical CPU count."""
    logical = os.cpu_count() or 1
    try:
        if sys.platform == "win32":
            found = windows_cores()
        elif sys.platform.startswith("linux"):
            found = linux_cores()
        else:
            raise OSError(f"no topology reader for {sys.platform}")
    except (OSError, ValueError) as exc:
        logger.warning("Cannot count physical cores (%s); using %d", exc, logical)
        return logical
    return max(1, min(found, logical))


def split(preset: Preset, cores: int) -> Budget:
    """Split `cores` between pool threads and native threads per `preset`."""
    match preset:
        case "latency":
            threads = 1
        case "balanced":
            threads = max(2, cores // 4)
        case "throughput":
            threads = cores
    return Budget(cores, threads, max(1, cores // threads))


def budget(preset: Preset, physical: int, cap: int | None, reserve: int) -> Budget:
    """Return the budget left after `reserve` cores and the optional `cap`."""
    cores = max(1, physical - reserve)
    if cap is not None:
        cores = max(1, min(cores, cap))
    return split(preset, cores)
