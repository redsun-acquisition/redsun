"""Read the shape of a plan parameter's annotation.

Plain Python with no toolkit: the plan spec decides from these shapes whether
a parameter can be shown, and the Qt view builds its widgets from them.
"""

from __future__ import annotations

import types
from types import NoneType
from typing import Annotated, Any, Union, get_args, get_origin

import annotated_types as at


def safe_issubclass(cls: Any, parent: Any) -> bool:
    """`issubclass` returning `False` instead of raising `TypeError`."""
    try:
        return issubclass(cls, parent)
    except TypeError:
        return False


def unwrap(ann: Any) -> Any:
    """Return *ann* without the metadata of `Annotated`, at its outer level."""
    while get_origin(ann) is Annotated:
        ann = get_args(ann)[0]
    return ann


def metadata(ann: Any) -> tuple[Any, ...]:
    """Return the `Annotated` metadata of *ann* at its outer level, none for a bare type."""
    if get_origin(ann) is not Annotated:
        return ()
    return get_args(ann)[1:]


def limits_of(items: tuple[Any, ...]) -> list[at.BaseMetadata]:
    """Return the `annotated-types` limits among *items*, a group such as `Interval` opened."""
    found: list[at.BaseMetadata] = []
    for item in items:
        if isinstance(item, at.GroupedMetadata):
            found.extend(limits_of(tuple(item)))
        elif isinstance(item, at.BaseMetadata):
            found.append(item)
    return found


def has_limits(ann: Any) -> bool:
    """Return True if *ann* carries an `annotated-types` limit at any level."""
    if limits_of(metadata(ann)):
        return True
    return any(has_limits(arg) for arg in get_args(unwrap(ann)))


def max_length(ann: Any) -> int | None:
    """Return the most items *ann*'s outer limits allow, or `None` without such a limit."""
    lengths = [
        limit.max_length
        for limit in limits_of(metadata(ann))
        if isinstance(limit, at.MaxLen)
    ]
    return min(lengths) if lengths else None


def union_members(ann: Any) -> tuple[Any, ...]:
    """Return the members of a union annotation, or an empty tuple for any other."""
    origin = get_origin(ann)
    if origin is Union or origin is types.UnionType:
        return get_args(ann)
    return ()


def without_none(members: tuple[Any, ...]) -> Any:
    """Return the union of *members* other than `None`, or the one member left."""
    rest = tuple(member for member in members if member is not NoneType)
    return rest[0] if len(rest) == 1 else Union[rest]  # noqa: UP007


def is_mapping(ann: Any) -> bool:
    """Return True for a two-argument annotation whose origin a `dict` satisfies."""
    return len(get_args(ann)) == 2 and safe_issubclass(dict, get_origin(ann))


def is_fixed_tuple(ann: Any) -> bool:
    """Return True for `tuple[A, B, ...]` of fixed length."""
    args = get_args(ann)
    return get_origin(ann) is tuple and bool(args) and Ellipsis not in args


def container_type(ann: Any) -> type | None:
    """Return the built-in that fills a one-element container annotation.

    `list` for `Sequence[T]`, `Iterable[T]` and any other origin a list
    satisfies, `tuple` for `tuple[T, ...]`, `set` for `AbstractSet[T]` and
    `set[T]`, `frozenset` for `frozenset[T]`, and `None` for any other
    annotation.
    """
    origin, args = get_origin(ann), get_args(ann)
    if origin is tuple:
        return tuple if len(args) == 2 and args[1] is Ellipsis else None
    if origin is None or len(args) != 1:
        return None
    for built in (list, set, frozenset):
        if safe_issubclass(built, origin):
            return built
    return None
