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
    """Get a list of model names that implement a specific protocol.

    Parameters
    ----------
    devices : ``Mapping[str, PDevice]``
        Mapping of model names to model instances.
    proto : ``type[P]``
        The protocol type to filter for.
    choices : ``Sequence[str]``
        Sequence of model names to consider.

    Returns
    -------
    ``list[P]``
        List of model names that implement the given protocol.
    """
    return [
        model
        for name, model in devices.items()
        if isinstance(model, proto) and name in choices
    ]


def _is_pdevice_annotation(ann: Any) -> bool:
    """Return True if *ann* is a class or Protocol that has ``PDevice`` in its MRO.

    This is the correct way to ask "is this annotation a device protocol/class?"
    when working with *type* objects rather than instances.  Plain
    ``isinstance(ann, PDevice)`` checks whether the *type object itself* satisfies
    the PDevice structural protocol — which it never does.  Checking the MRO is
    both fast and safe, and works for concrete classes and Protocol subclasses alike.
    """
    return PDevice in getattr(ann, "__mro__", ())


def issequence(ann: Any) -> bool:
    """Return True if *ann* is a ``Sequence[...]`` generic alias.

    Notes
    -----
    ``str`` and ``bytes`` are sequences in the stdlib sense, but the annotation
    ``str`` is *not* a generic alias — ``get_origin(str)`` returns ``None`` —
    so they are naturally excluded here.
    """
    origin = get_origin(ann)
    if origin is None:
        return False
    try:
        return issubclass(origin, Sequence)
    except TypeError:
        return False


def isdevicesequence(ann: Any) -> bool:
    """Return True if *ann* is a ``Sequence[T]`` where ``T`` is a ``PDevice`` type."""
    if not issequence(ann):
        return False
    args = get_args(ann)
    return len(args) == 1 and _is_pdevice_annotation(args[0])


def isdevice(ann: Any) -> bool:
    """Return True if *ann* is a class/Protocol that is a subtype of ``PDevice``.

    This operates on *type annotations* (i.e. the class/protocol itself), not on
    instances.  The previous implementation used ``isinstance(ann, PDevice)``,
    which checked whether the type object is itself a structural instance of the
    PDevice protocol — always ``False``.
    """
    return _is_pdevice_annotation(ann)
