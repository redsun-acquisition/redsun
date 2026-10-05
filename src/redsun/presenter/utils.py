"""Predicates and helpers inspecting plan parameters.

`create_plan_spec` uses them to classify annotations, and `resolve_arguments`
to turn device names into [`Device`][ophyd_async.core.Device] instances.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from typing import Any, TypeVar, get_args, get_origin

from ophyd_async.core import Device as OADevice

__all__ = [
    "device_class",
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
    """Return the devices named in *choices* that are instances of *proto*.

    Parameters
    ----------
    devices
        Devices by name.
    proto
        Class checked with `isinstance`.
    choices
        Names of the devices to consider.
    """
    return [
        model
        for name, model in devices.items()
        if isinstance(model, proto) and name in choices
    ]


def device_class(ann: Any) -> Any:
    """Return what devices are checked against for *ann*: its origin when it has type arguments.

    `Readable[Any]` gives `Readable`, since `isinstance` takes no type
    arguments; any other annotation is returned unchanged.
    """
    origin = get_origin(ann)
    return origin if origin is not None and _is_device_annotation(origin) else ann


def _is_device_annotation(ann: Any) -> bool:
    """Return True if *ann* is a [`Device`][ophyd_async.core.Device] subclass or a `@runtime_checkable Protocol`.

    Any `@runtime_checkable` Protocol is accepted, with or without type
    arguments; each device is checked later with `isinstance` against the
    class without them.
    """
    origin = get_origin(ann)
    if origin is not None:
        ann = origin
    try:
        if issubclass(ann, OADevice):
            return True
    except TypeError:
        return False
    # a Protocol cannot inherit a concrete class, so a device protocol cannot
    # inherit Device
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
    """Return True if *ann* is a `Sequence[...]` generic alias.

    Notes
    -----
    `str` and `bytes` are sequences, but not generic aliases
    (`get_origin(str)` is `None`), so they are excluded.
    """
    return _origin_subclasses(ann, Sequence)


def isdevicesequence(ann: Any) -> bool:
    """Return True if *ann* is `Sequence[T]` where *T* is a [`Device`][ophyd_async.core.Device] subtype."""
    return issequence(ann) and _single_device_arg(ann)


def isdeviceset(ann: Any) -> bool:
    """Return True if *ann* is `Set[T]` (or `AbstractSet[T]`, `FrozenSet[T]`) where *T* is a [`Device`][ophyd_async.core.Device] subtype."""
    return _origin_subclasses(ann, AbstractSet) and _single_device_arg(ann)


def isdevice(ann: Any) -> bool:
    """Return True if the annotation *ann* is a [`Device`][ophyd_async.core.Device] subclass."""
    return _is_device_annotation(ann)
