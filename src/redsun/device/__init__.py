"""redsun device layer — re-exports from ophyd-async.

The redsun device layer delegates entirely to ophyd-async.
Import device primitives from here; do not import from ophyd_async directly
within redsun application code.
"""

from __future__ import annotations

from ophyd_async.core import (
    AsyncStatus,
    DetectorArmLogic,
    DetectorDataLogic,
    DetectorTrigger,
    DetectorTriggerLogic,
    Device,
    FlyerController,
    SignalR,
    SignalRW,
    SignalW,
    SignalX,
    StandardDetector,
    StandardFlyer,
    StandardReadable,
    StandardReadableFormat,
    TriggerInfo,
    WatchableAsyncStatus,
    soft_signal_r_and_setter,
    soft_signal_rw,
)

from .protocols import HasCache

__all__ = [
    "AsyncStatus",
    "DetectorArmLogic",
    "DetectorDataLogic",
    "DetectorTrigger",
    "DetectorTriggerLogic",
    "Device",
    "FlyerController",
    "HasCache",
    "SignalR",
    "SignalRW",
    "SignalW",
    "SignalX",
    "StandardDetector",
    "StandardFlyer",
    "StandardReadable",
    "StandardReadableFormat",
    "TriggerInfo",
    "WatchableAsyncStatus",
    "soft_signal_r_and_setter",
    "soft_signal_rw",
]
