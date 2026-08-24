from __future__ import annotations

import inspect
from functools import cache
from itertools import product
from typing import TYPE_CHECKING, Any

from typing_extensions import get_protocol_members

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["problems"]

_PROBE = object()


@cache
def _methods(protocol: type) -> frozenset[str]:
    """Return the member names of *protocol* that must be callable.

    The rest are data members, which only an instance can be asked about.
    """
    return frozenset(
        name
        for name in get_protocol_members(protocol)
        if _call_signature(protocol, name) is not None
    )


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
            for name in sorted(get_protocol_members(protocol) - _methods(protocol))
            if not hasattr(candidate, name)
        )
    return found


@cache
def _signature_problems(cls: type, protocol: type) -> tuple[str, ...]:
    found: list[str] = []
    for name in sorted(_methods(protocol)):
        wanted = _call_signature(protocol, name)
        if wanted is None:
            continue
        if not callable(getattr(cls, name, None)):
            found.append(
                f"{name!r} is not callable"
                if hasattr(cls, name)
                else f"{name!r} is missing"
            )
            continue
        got = _call_signature(cls, name)
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


def _call_signature(owner: type, name: str) -> inspect.Signature | None:
    """How *name* is called on an instance of *owner*, if that is knowable.

    ``None`` for a data member, and for a callable whose signature cannot be
    read. Binding through the descriptor protocol is what drops ``self`` from
    a method and leaves a ``staticmethod`` untouched.
    """
    static = inspect.getattr_static(owner, name, None)
    if isinstance(static, property):
        return None
    bound = static.__get__(object()) if hasattr(static, "__get__") else static
    if not callable(bound):
        return None
    try:
        return inspect.signature(bound)
    except (TypeError, ValueError):
        return None


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
    for only_required, positionally in product((False, True), repeat=2):
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
