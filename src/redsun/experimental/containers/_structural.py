from __future__ import annotations

import inspect
from functools import cache
from typing import TYPE_CHECKING, Any

from typing_extensions import get_protocol_members

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["members", "methods", "problems", "satisfies"]

_PROBE = object()


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
        name for name in members(protocol) if _wanted(protocol, name) is not None
    )


def satisfies(candidate: type | object, protocol: type) -> bool:
    """Whether *candidate* satisfies *protocol*."""
    return not problems(candidate, protocol)


def problems(candidate: type | object, protocol: type) -> list[str]:
    """Every reason *candidate* fails to satisfy *protocol*.

    Callable members are compared by signature: the implementation must accept
    every call the protocol permits, so a renamed parameter or an extra
    required one is a mismatch, while an extra defaulted parameter is not.
    Types are not compared; a type checker does that at the call site.

    Data members are read off an instance, because a value assigned in
    ``__init__`` cannot be seen on the class. Passing a class therefore leaves
    them unchecked, and passing an instance checks everything.
    """
    cls = candidate if isinstance(candidate, type) else type(candidate)
    found = list(_signature_problems(cls, protocol))
    if not isinstance(candidate, type):
        found.extend(
            f"{name!r} is missing"
            for name in sorted(members(protocol) - methods(protocol))
            if not hasattr(candidate, name)
        )
    return found


@cache
def _signature_problems(cls: type, protocol: type) -> tuple[str, ...]:
    found: list[str] = []
    for name in sorted(methods(protocol)):
        wanted = _wanted(protocol, name)
        if wanted is None:
            continue
        if not callable(getattr(cls, name, None)):
            found.append(
                f"{name!r} is not callable"
                if hasattr(cls, name)
                else f"{name!r} is missing"
            )
            continue
        got = _offered(cls, name)
        if got is None:
            continue
        reason = _mismatch(wanted, got)
        if reason is not None:
            found.append(
                f"{_rendered(name, got)} cannot be called as "
                f"{_rendered(name, wanted)}: {reason}"
            )
    return tuple(found)


def _rendered(name: str, signature: inspect.Signature) -> str:
    """Spell out a call, without the types, which are not what was compared."""
    bare = signature.replace(
        parameters=[
            param.replace(annotation=inspect.Parameter.empty)
            for param in signature.parameters.values()
        ],
        return_annotation=inspect.Signature.empty,
    )
    return f"{name}{bare}"


def _wanted(protocol: type, name: str) -> inspect.Signature | None:
    """How *protocol* says *name* is called, or ``None`` if it is a data member."""
    member = inspect.getattr_static(protocol, name, None)
    if isinstance(member, (staticmethod, classmethod)):
        member = member.__func__
    if not inspect.isfunction(member):
        return None
    return _without_self(inspect.signature(member))


def _offered(cls: type, name: str) -> inspect.Signature | None:
    """How *name* can be called on an instance of *cls*, if that is knowable."""
    static = inspect.getattr_static(cls, name, None)
    if isinstance(static, property):
        return None
    try:
        if isinstance(static, staticmethod):
            return inspect.signature(static.__func__)
        if isinstance(static, classmethod):
            return _without_self(inspect.signature(static.__func__))
        member = getattr(cls, name)
        signature = inspect.signature(member)
    except (TypeError, ValueError):
        return None
    return _without_self(signature) if inspect.isfunction(member) else signature


def _without_self(signature: inspect.Signature) -> inspect.Signature:
    parameters = list(signature.parameters.values())
    return signature.replace(parameters=parameters[1:])


def _mismatch(wanted: inspect.Signature, got: inspect.Signature) -> str | None:
    for args, kwargs in _probes(wanted):
        try:
            got.bind(*args, **kwargs)
        except TypeError as e:
            return str(e)
    return None


def _probes(
    wanted: inspect.Signature,
) -> Iterator[tuple[list[Any], dict[str, Any]]]:
    """Yield the calls *wanted* permits, which an implementation must accept.

    Three are enough to pin a signature: every parameter passed the way the
    protocol names it, only the required ones, and everything that may travel
    positionally doing so.
    """
    seen: list[tuple[list[Any], dict[str, Any]]] = []
    for only_required in (False, True):
        for positionally in (False, True):
            probe = _probe(wanted, only_required, positionally)
            if probe not in seen:
                seen.append(probe)
                yield probe


def _probe(
    wanted: inspect.Signature, only_required: bool, positionally: bool
) -> tuple[list[Any], dict[str, Any]]:
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    for param in wanted.parameters.values():
        if only_required and param.default is not param.empty:
            continue
        if param.kind is param.VAR_POSITIONAL or param.kind is param.POSITIONAL_ONLY:
            args.append(_PROBE)
        elif param.kind is param.VAR_KEYWORD:
            kwargs["_probe"] = _PROBE
        elif param.kind is param.KEYWORD_ONLY or not positionally:
            kwargs[param.name] = _PROBE
        else:
            args.append(_PROBE)
    return args, kwargs
