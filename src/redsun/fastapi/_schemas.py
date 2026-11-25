"""The JSON Schema of every type a presenter serves."""

from __future__ import annotations

import inspect
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter
from pydantic.errors import PydanticUserError

if TYPE_CHECKING:
    from psygnal import SignalInstance

    from ..ports._remote import Served

Adapters = dict[Any, TypeAdapter[Any]]


def signal_adapters(
    presenter: object, serving: Served, adapters: Adapters
) -> dict[str, list[TypeAdapter[Any]]]:
    """Return the adapter of each argument of each signal *serving* lists, by signal name.

    Every parameter and return type of a command, the return type of a query
    and every argument type of a signal must have a JSON Schema. *adapters*
    holds the adapter already built for a type, and takes each new one.

    Raises
    ------
    TypeError
        If a type has no JSON Schema. The message lists every such type, one
        per line, each naming the member.
    """
    members = [
        *(
            (f"{c.name!r} takes a type with no JSON Schema ({p})", t)
            for c in serving.commands
            for p, t in c.parameters.items()
        ),
        *(
            (f"{c.name!r} returns a type with no JSON Schema", c.returns)
            for c in serving.commands
        ),
        *(
            (f"{q.name!r} returns a type with no JSON Schema", q.returns)
            for q in serving.queries
        ),
    ]
    problems = [
        f"{subject}: {problem}"
        for subject, t in members
        if isinstance(problem := adapter_of(t, adapters), str)
    ]
    found = {
        name: [adapter_of(t, adapters) for t in signal_types(signal)]
        for name, signal in serving.signals.items()
    }
    problems.extend(
        f"signal {name!r} has an argument type with no JSON Schema: {a}"
        for name, arguments in found.items()
        for a in arguments
        if isinstance(a, str)
    )
    if problems:
        raise TypeError(
            f"{type(presenter).__name__} cannot be served:\n"
            + "\n".join(f"- {p}" for p in problems)
        )
    return {
        name: [a for a in arguments if not isinstance(a, str)]
        for name, arguments in found.items()
    }


def signal_types(signal: SignalInstance) -> tuple[Any, ...]:
    """Return the argument types of *signal*, `Any` for an argument without one."""
    return tuple(
        Any if p.annotation is inspect.Parameter.empty else p.annotation
        for p in signal.signature.parameters.values()
    )


def adapter_of(t: Any, adapters: Adapters) -> TypeAdapter[Any] | str:
    """Return the adapter of *t*, or why *t* has no JSON Schema.

    An adapter is built once for a type that can be a dictionary key, and kept
    in *adapters*.
    """
    with suppress(KeyError, TypeError):
        return adapters[t]
    try:
        adapter = TypeAdapter[Any](t)
        adapter.json_schema()
    except PydanticUserError as error:
        return error.message
    with suppress(TypeError):
        adapters[t] = adapter
    return adapter


def signal_schema(
    adapters: dict[str, list[TypeAdapter[Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Return the JSON Schema of each argument of each signal, by signal name."""
    return {
        name: [adapter.json_schema() for adapter in arguments]
        for name, arguments in adapters.items()
    }
