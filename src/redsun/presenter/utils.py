"""Utility predicates and helpers for plan parameter inspection.

These functions are used by `create_plan_spec` to classify parameter
annotations and by `resolve_arguments` to resolve string device names
into live `PDevice` instances.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar, get_args, get_origin

from redsun.device import PDevice

__all__ = [
    "get_choice_list",
    "isdevice",
    "isdevicesequence",
    "issequence",
]

P = TypeVar("P", bound=PDevice)


def get_choice_list(
    devices: Mapping[str, PDevice], proto: type[P], choices: Sequence[str]
) -> list[P]:
    """Filter a device registry to those that match a protocol and are in *choices*.

    Parameters
    ----------
    devices : Mapping[str, PDevice]
        Mapping of device names to device instances.
    proto : type[P]
        Protocol or class to match against via ``isinstance``.
    choices : Sequence[str]
        Subset of device names to consider.

    Returns
    -------
    list[P]
        Device instances whose name is in *choices* and that satisfy *proto*.
    """
    return [
        model
        for name, model in devices.items()
        if isinstance(model, proto) and name in choices
    ]


def _is_pdevice_annotation(ann: Any) -> bool:
    """Return True if *ann* has `PDevice` in its MRO.

    This is the correct way to ask "is this annotation a device
    protocol/class?" when working with *type* objects rather than
    instances.  ``isinstance(ann, PDevice)`` checks whether the type
    object itself satisfies the structural protocol — which it never
    does.  Checking the MRO is fast, safe, and works for both concrete
    classes and Protocol subclasses.
    """
    return PDevice in getattr(ann, "__mro__", ())


def issequence(ann: Any) -> bool:
    """Return True if *ann* is a ``Sequence[...]`` generic alias.

    Notes
    -----
    ``str`` and ``bytes`` are sequences in the stdlib sense, but their
    annotations are not generic aliases (``get_origin(str)`` is ``None``),
    so they are naturally excluded.
    """
    origin = get_origin(ann)
    if origin is None:
        return False
    try:
        return issubclass(origin, Sequence)
    except TypeError:
        return False


def isdevicesequence(ann: Any) -> bool:
    """Return True if *ann* is ``Sequence[T]`` where *T* is a `PDevice` subtype."""
    if not issequence(ann):
        return False
    args = get_args(ann)
    return len(args) == 1 and _is_pdevice_annotation(args[0])


def isdevice(ann: Any) -> bool:
    """Return True if *ann* is a class or Protocol that subclasses `PDevice`.

    Operates on type annotations (the class itself), not on instances.
    """
    return _is_pdevice_annotation(ann)
