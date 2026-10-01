"""Runtime protocol checking."""

from __future__ import annotations

import inspect
from functools import cache
from itertools import product
from typing import TYPE_CHECKING, Any, Final, TypeVar, cast, get_origin, overload

from typing_extensions import get_protocol_members, is_protocol

if TYPE_CHECKING:
    from collections.abc import Iterator

    from typing_extensions import TypeForm, TypeIs

__all__ = [
    "is_protocol_class",
    "members",
    "methods",
    "problems",
    "protocol_of",
    "satisfies",
]

P = TypeVar("P")

PROBE: Final = object()
"""The argument passed for every parameter of a probing call."""

MISSING: Final = object()
"""What `defined` returns for a name no class in the MRO defines."""


def is_protocol_class(candidate: object) -> TypeIs[type]:
    """Whether *candidate* is a protocol class, not a class inheriting one."""
    return isinstance(candidate, type) and is_protocol(candidate)


def protocol_of(hint: object) -> type | None:
    """Return the protocol *hint* names, subscripted or not, or `None`."""
    if is_protocol_class(hint):
        return hint
    origin = get_origin(hint)
    return origin if is_protocol_class(origin) else None


@cache
def members(protocol: type) -> frozenset[str]:
    """Return the member names *protocol* requires."""
    return frozenset(get_protocol_members(protocol))


@cache
def methods(protocol: type) -> frozenset[str]:
    """Return the member names of *protocol* that must be callable.

    The rest are data members, which only an instance can be asked about.
    """
    return frozenset(
        name for name in members(protocol) if call_signature(protocol, name) is not None
    )


@overload
def satisfies(candidate: type, protocol: TypeForm[P]) -> bool: ...
@overload
def satisfies(candidate: object, protocol: TypeForm[P]) -> TypeIs[P]: ...
def satisfies(candidate: object, protocol: object) -> bool:
    """Whether *candidate* satisfies *protocol*.

    An instance that does is narrowed to *protocol* for a type checker; a class
    is not, since it is not an instance of the protocol it satisfies.
    """
    # a protocol is a class at runtime, which is what `problems` inspects
    return not problems(candidate, cast("type", protocol))


def problems(candidate: type | object, protocol: type) -> list[str]:
    """Every reason *candidate* fails to satisfy *protocol*.

    Callable members are compared by signature: the implementation must accept
    every call the protocol allows, so a renamed or extra required parameter
    fails and an extra defaulted one does not. Types are not compared; a type
    checker does that.

    Data members are read from an instance, since a value assigned in
    `__init__` is not on the class. A class leaves them unchecked; an
    instance checks everything.
    """
    cls = candidate if isinstance(candidate, type) else type(candidate)
    found = list(signature_problems(cls, protocol))
    if not isinstance(candidate, type):
        found.extend(
            f"{name!r} is missing"
            for name in sorted(members(protocol) - methods(protocol))
            if not hasattr(candidate, name)
        )
    return found


@cache
def signature_problems(cls: type, protocol: type) -> tuple[str, ...]:
    """Return why the methods of *cls* cannot be called as *protocol* calls them."""
    found: list[str] = []
    for name in sorted(methods(protocol)):
        wanted = call_signature(protocol, name)
        if wanted is None:
            continue
        if defined(cls, name) is MISSING:
            found.append(f"{name!r} is missing")
            continue
        if not callable(getattr(cls, name)):
            found.append(f"{name!r} is not callable")
            continue
        got = call_signature(cls, name)
        if got is None:
            continue
        reason = mismatch(wanted, got)
        if reason is not None:
            found.append(
                f"{rendered(name, got)} cannot be called as "
                f"{rendered(name, wanted)}: {reason}"
            )
    return tuple(found)


def rendered(name: str, signature: inspect.Signature) -> str:
    """Spell out a call, without the types, which are not what was compared."""
    bare = signature.replace(
        parameters=[
            param.replace(annotation=inspect.Parameter.empty)
            for param in signature.parameters.values()
        ],
        return_annotation=inspect.Signature.empty,
    )
    return f"{name}{bare}"


def defined(owner: type, name: str) -> Any:
    """Return *name* as *owner* or one of its bases defines it.

    Unlike `inspect.getattr_static`, the metaclass is not searched.
    """
    # every class reaches type.__call__ through its metaclass, which says
    # nothing about whether its instances can be called
    for klass in owner.__mro__:
        if name in vars(klass):
            return vars(klass)[name]
    return MISSING


def call_signature(owner: type, name: str) -> inspect.Signature | None:
    """How *name* is called on an instance of *owner*, if that is knowable.

    `None` for a data member or an unreadable signature. Binding through the
    descriptor protocol drops `self` from a method and leaves a
    `staticmethod` as is.
    """
    static = defined(owner, name)
    if static is MISSING or isinstance(static, property):
        return None
    bound = static.__get__(object()) if hasattr(static, "__get__") else static
    if not callable(bound):
        return None
    try:
        return inspect.signature(bound)
    except (TypeError, ValueError):
        return None


def mismatch(wanted: inspect.Signature, got: inspect.Signature) -> str | None:
    """Return why *got* refuses a call *wanted* permits, `None` when it refuses none."""
    for args, kwargs in probes(wanted):
        try:
            got.bind(*args, **kwargs)
        except TypeError as e:
            return str(e)
    return None


def probes(
    wanted: inspect.Signature,
) -> Iterator[tuple[list[Any], dict[str, Any]]]:
    """Yield the calls *wanted* permits, which an implementation must accept.

    Three calls pin a signature: every parameter as the protocol names it, only
    the required ones, and every positional-capable one passed positionally.
    """
    seen: list[tuple[list[Any], dict[str, Any]]] = []
    for only_required, positionally in product((False, True), repeat=2):
        call = probe(wanted, only_required, positionally)
        if call not in seen:
            seen.append(call)
            yield call


def probe(
    wanted: inspect.Signature, only_required: bool, positionally: bool
) -> tuple[list[Any], dict[str, Any]]:
    """Return the arguments of one call *wanted* permits.

    Parameters
    ----------
    only_required
        Leave out every parameter carrying a default.
    positionally
        Pass a parameter that can be given either way by position.
    """
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    for param in wanted.parameters.values():
        if only_required and param.default is not param.empty:
            continue
        if param.kind is param.VAR_POSITIONAL or param.kind is param.POSITIONAL_ONLY:
            args.append(PROBE)
        elif param.kind is param.VAR_KEYWORD:
            kwargs["_probe"] = PROBE
        elif param.kind is param.KEYWORD_ONLY or not positionally:
            kwargs[param.name] = PROBE
        else:
            args.append(PROBE)
    return args, kwargs
