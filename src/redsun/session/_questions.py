from __future__ import annotations

from collections.abc import Mapping
from types import UnionType
from typing import TYPE_CHECKING, Any, Literal, Union, get_args, get_origin

from .._structural import problems, protocol_of
from ..injection._census import satisfying

if TYPE_CHECKING:
    from collections.abc import Iterable

    from typing_extensions import TypeForm

__all__ = [
    "NoAnswer",
    "Shape",
    "answer",
    "is_protocol_union",
    "is_union",
    "optional_arg",
    "shape_of",
]

Shape = Literal["one", "maybe", "every"]


class NoAnswer(LookupError):
    """Nothing in the session satisfies a protocol one answer was demanded for."""


def is_union(hint: TypeForm[Any]) -> bool:
    """Return whether *hint* is a union, written as `X | Y` or `Union[X, Y]`."""
    return get_origin(hint) in (Union, UnionType)


def optional_arg(hint: TypeForm[Any]) -> TypeForm[Any] | None:
    """Return `X` for `X | None`, or `None` for anything else."""
    if not is_union(hint):
        return None
    args = [arg for arg in get_args(hint) if arg is not type(None)]
    return args[0] if len(args) == 1 else None


def is_protocol_union(hint: TypeForm[Any]) -> bool:
    """Whether *hint* is a union of more than one type, a protocol among them."""
    if not is_union(hint):
        return False
    options = [arg for arg in get_args(hint) if arg is not type(None)]
    return len(options) > 1 and any(protocol_of(option) for option in options)


def shape_of(hint: TypeForm[Any]) -> tuple[Shape, type] | None:
    """Return how many answers *hint* asks for, and about which protocol.

    A protocol `P` asks for exactly one object satisfying it, `P | None`
    for at most one, and `Mapping[str, P]` for every component satisfying
    it. A subscripted generic protocol is matched as its unsubscripted class.
    `None` for any other hint, which names a value.
    """
    protocol = protocol_of(hint)
    if protocol is not None:
        return "one", protocol
    if is_union(hint):
        protocol = protocol_of(optional_arg(hint))
        return None if protocol is None else ("maybe", protocol)
    args = get_args(hint)
    if get_origin(hint) is Mapping and len(args) == 2 and args[0] is str:
        protocol = protocol_of(args[1])
        if protocol is not None:
            return "every", protocol
    return None


def answer(
    shape: Shape,
    protocol: type,
    asker: str,
    components: Mapping[str, object],
    shared: Iterable[tuple[str, object]],
    where: str,
) -> tuple[object, list[str]]:
    """Answer one question, returning the answer and the components it came from.

    A census reads *components* alone and includes *asker*. One answer is
    looked for among *components* and the values in *shared*, each paired with
    the component sharing it, and never comes from *asker*; an object reached
    both ways counts once.

    Raises
    ------
    TypeError
        If several objects answer where one was asked for.
    NoAnswer
        If none answers where exactly one was asked for.
    """
    if shape == "every":
        found: dict[str, object] = satisfying(components, protocol)
        return found, list(found)
    matches: dict[int, tuple[str, object]] = {}
    for owner, candidate in [*components.items(), *shared]:
        if owner != asker and not problems(candidate, protocol):
            matches.setdefault(id(candidate), (owner, candidate))
    if len(matches) > 1:
        owners = ", ".join(sorted(repr(owner) for owner, _ in matches.values()))
        raise TypeError(
            f"{where} asks for the one object satisfying {protocol.__name__!r}, "
            f"but {len(matches)} do, from {owners}. Narrow the protocol, or ask "
            f"for 'Mapping[str, {protocol.__name__}]'."
        )
    if not matches:
        if shape == "maybe":
            return None, []
        raise NoAnswer(
            f"{where} asks for the one object satisfying {protocol.__name__!r}, "
            "and nothing in the session does"
        )
    ((owner, found_one),) = matches.values()
    return found_one, [owner]
