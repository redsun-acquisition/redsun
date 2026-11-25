"""The `remote` marker and what a presenter serves with it."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar, get_type_hints

from ._wiring import marker_of, port_name, ports

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from psygnal import SignalInstance

__all__ = [
    "REMOTE_ATTR",
    "Command",
    "Query",
    "Served",
    "is_remote",
    "remote",
    "served",
]

F = TypeVar("F", bound="Callable[..., Any]")

REMOTE_ATTR = "__redsun_remote__"

UNNAMEABLE = (
    inspect.Parameter.POSITIONAL_ONLY,
    inspect.Parameter.VAR_POSITIONAL,
    inspect.Parameter.VAR_KEYWORD,
)


def remote(fn: F, /) -> F:
    """Mark a method as reachable from outside the process.

    Written directly on the `def`, below `@slot` or `@property`.

    Raises
    ------
    TypeError
        If the target is not a plain function, or already carries `@slot`.
    """
    if not inspect.isfunction(fn) or marker_of(fn) is not None:
        raise TypeError(
            f"cannot mark {fn!r} as remote: @remote goes directly on the def, "
            "below @slot or @property"
        )
    setattr(fn, REMOTE_ATTR, True)
    return fn


def is_remote(fn: object) -> bool:
    """Return whether *fn* carries `remote`."""
    return getattr(fn, REMOTE_ATTR, False) is True


@dataclass(frozen=True, slots=True)
class Command:
    """A remote slot of a built presenter."""

    name: str
    """The port name."""

    call: Callable[..., Awaitable[object]]
    """The slot, bound to the presenter."""

    parameters: dict[str, Any]
    """Parameter types by name, `Any` for a parameter without an annotation."""

    returns: Any
    """The return type, `Any` without an annotation."""


@dataclass(frozen=True, slots=True)
class Query:
    """A remote property of a built presenter."""

    name: str
    """The property name."""

    read: Callable[[], object]
    """Read the property on the presenter."""

    returns: Any
    """The getter's return type, `Any` without an annotation."""


@dataclass(frozen=True, slots=True)
class Served:
    """What a built presenter makes reachable from outside the process."""

    commands: tuple[Command, ...]
    """Remote slots."""

    queries: tuple[Query, ...]
    """Remote properties."""

    signals: dict[str, SignalInstance]
    """Every public signal, by port name."""


def served(component: object) -> Served | None:
    """Return what *component* serves, `None` when no member is `remote`.

    Raises
    ------
    TypeError
        If a remote member breaks a rule. The message lists every problem, one
        per line, each naming the member.
    """
    cls = type(component)
    problems: list[str] = []
    commands: list[Command] = []
    queries: list[Query] = []

    for attr in dir(cls):
        declared = getattr(cls, attr, None)
        if isinstance(declared, property):
            if is_remote(declared.fget):
                query = read_query(component, attr, declared, problems)
                if query is not None:
                    queries.append(query)
        elif inspect.isfunction(declared) and is_remote(declared):
            command = read_command(component, attr, declared, problems)
            if command is not None:
                commands.append(command)

    if problems:
        raise TypeError(
            f"{cls.__name__} cannot be served:\n"
            + "\n".join(f"- {p}" for p in problems)
        )
    if not commands and not queries:
        return None
    return Served(tuple(commands), tuple(queries), ports(component).signals)


def read_command(
    component: object,
    attr: str,
    function: Callable[..., Any],
    problems: list[str],
) -> Command | None:
    """Return the command for a remote method, or `None` after recording what is wrong."""
    marker = marker_of(function)
    if marker is None:
        problems.append(f"{attr!r} is @remote but not a @slot")
        return None
    if not inspect.iscoroutinefunction(function):
        problems.append(f"{attr!r} is a remote slot and must be async def")
        return None
    hints = resolve_hints(function, attr, problems)
    if hints is None:
        return None
    parameters: dict[str, Any] = {}
    refused = False
    for p in list(inspect.signature(function).parameters.values())[1:]:
        if p.kind in UNNAMEABLE:
            problems.append(
                f"{attr!r} has a {p.kind.description} parameter ({p.name}), "
                "which a remote call cannot pass by name"
            )
            refused = True
        else:
            parameters[p.name] = hints.get(p.name, Any)
    if refused:
        return None
    method = getattr(component, attr)
    return Command(port_name(method), method, parameters, hints.get("return", Any))


def read_query(
    component: object,
    attr: str,
    declared: property,
    problems: list[str],
) -> Query | None:
    """Return the query for a remote property, or `None` after recording what is wrong."""
    getter = declared.fget
    if getter is None:
        return None
    if inspect.iscoroutinefunction(getter):
        problems.append(
            f"{attr!r} is a remote property with an async getter: "
            "use an async remote slot that returns the value"
        )
        return None
    hints = resolve_hints(getter, attr, problems)
    if hints is None:
        return None
    return Query(attr, lambda: getattr(component, attr), hints.get("return", Any))


def resolve_hints(
    function: Callable[..., Any], attr: str, problems: list[str]
) -> dict[str, Any] | None:
    """Return the resolved annotations of *function*, or `None` after recording the unresolved name."""
    try:
        return get_type_hints(function, include_extras=True)
    except NameError as error:
        problems.append(f"{attr!r} has annotations that do not resolve: {error}")
        return None
