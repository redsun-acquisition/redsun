"""Utility predicates and helpers for plan parameter inspection.

These functions are used by `create_plan_spec` to classify parameter
annotations and by `resolve_arguments` to resolve string device names
into live [`Device`][ophyd_async.core.Device] instances.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from typing import Any, TypeVar, get_args, get_origin

from ophyd_async.core import Device as OADevice

__all__ = [
    "get_choice_list",
    "isdevice",
    "isdevicesequence",
    "isdeviceset",
    "issequence",
]

D = TypeVar("D", bound=OADevice)


def get_choice_list(
    devices: Mapping[str, OADevice], proto: type[D], choices: Sequence[str]
) -> list[D]:
    """Filter a device registry to those that match a protocol and are in *choices*.

    Parameters
    ----------
    devices : Mapping[str, OADevice]
        Mapping of device names to device instances.
    proto : type[D]
        Class to match against via ``isinstance``.
    choices : Sequence[str]
        Subset of device names to consider.

    Returns
    -------
    list[D]
        Device instances whose name is in *choices* and that satisfy *proto*.
    """
    return [
        model
        for name, model in devices.items()
        if isinstance(model, proto) and name in choices
    ]


def _is_device_annotation(ann: Any) -> bool:
    """Return True if *ann* is a [`Device`][ophyd_async.core.Device] subclass or a ``@runtime_checkable Protocol``.

    Python 3.11 forbids Protocols from inheriting non-Protocol concrete classes,
    so device-protocol annotations (e.g. ``_MotorProtocol``) cannot inherit from
    ``Device`` directly.  As a pragmatic extension, any ``@runtime_checkable``
    Protocol is accepted here - the actual per-device structural check is
    performed later via ``isinstance(device, proto)``.
    """
    try:
        if issubclass(ann, OADevice):
            return True
    except TypeError:
        return False
    return isinstance(ann, type) and getattr(ann, "_is_runtime_protocol", False)


def _origin_subclasses(ann: Any, base: type) -> bool:
    """Return True if *ann* is a generic alias whose origin subclasses *base*."""
    origin = get_origin(ann)
    if origin is None:
        return False
    try:
        return issubclass(origin, base)
    except TypeError:
        return False


def _single_device_arg(ann: Any) -> bool:
    """Return True if *ann* takes exactly one parameter and it is a device."""
    args = get_args(ann)
    return len(args) == 1 and _is_device_annotation(args[0])


def issequence(ann: Any) -> bool:
    """Return True if *ann* is a ``Sequence[...]`` generic alias.

    Notes
    -----
    ``str`` and ``bytes`` are sequences in the stdlib sense, but their
    annotations are not generic aliases (``get_origin(str)`` is ``None``),
    so they are naturally excluded.
    """
    return _origin_subclasses(ann, Sequence)


def isdevicesequence(ann: Any) -> bool:
    """Return True if *ann* is ``Sequence[T]`` where *T* is a [`Device`][ophyd_async.core.Device] subtype."""
    return issequence(ann) and _single_device_arg(ann)


def isdeviceset(ann: Any) -> bool:
    """Return True if *ann* is ``Set[T]`` (or ``AbstractSet[T]``, ``FrozenSet[T]``) where *T* is a [`Device`][ophyd_async.core.Device] subtype."""
    return _origin_subclasses(ann, AbstractSet) and _single_device_arg(ann)


def isdevice(ann: Any) -> bool:
    """Return True if *ann* is a class that subclasses [`Device`][ophyd_async.core.Device].

    Operates on type annotations (the class itself), not on instances.
    """
    return _is_device_annotation(ann)
