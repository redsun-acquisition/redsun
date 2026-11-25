"""The JSON Schema of every type a presenter serves, and the AsyncAPI document."""

from __future__ import annotations

import inspect
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter
from pydantic.errors import PydanticUserError

from redsun import __version__

if TYPE_CHECKING:
    from psygnal import SignalInstance

    from ..ports._remote import Served

Adapters = dict[Any, TypeAdapter[Any]]
NAMED = frozenset({"properties", "patternProperties", "$defs", "definitions"})
"""Keys whose value maps names, which are not schema keywords, to schemas."""
DATA = frozenset({"const", "default", "enum", "examples"})
"""Keys whose value is data, never rewritten."""


def check_schemas(
    presenter: object, serving: Served, adapters: Adapters
) -> dict[str, list[TypeAdapter[Any]]]:
    """Check that every type *serving* names has a JSON Schema.

    Every parameter and return type of a command, the return type of a query
    and every argument type of a signal must have one. Return the adapter of
    each argument of each signal, by signal name. *adapters* holds the adapter
    already built for a type, and takes each new one.

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


def asyncapi_document(
    title: str, signals: dict[str, dict[str, list[TypeAdapter[Any]]]]
) -> dict[str, Any]:
    """Return the AsyncAPI 3.0.0 document of the messages sent on `/api/events`.

    *signals* holds the adapter of each argument of each signal, by presenter
    and signal name. Each signal is a message named `{presenter}.{signal}`,
    and every type a message refers to is in `components.schemas`. The
    schemas are JSON Schema draft-07, the dialect AsyncAPI 3.0.0 reads.
    """
    keyed = [
        ((presenter, signal, i), "serialization", adapter)
        for presenter, by_signal in signals.items()
        for signal, adapters in by_signal.items()
        for i, adapter in enumerate(adapters)
    ]
    schemas, top = TypeAdapter.json_schemas(
        keyed, ref_template="#/components/schemas/{model}"
    )
    messages: dict[str, dict[str, Any]] = {}
    for presenter, by_signal in signals.items():
        for signal, adapters in by_signal.items():
            arguments = [
                draft07(schemas[(presenter, signal, i), "serialization"])
                for i in range(len(adapters))
            ]
            title_case = "".join(
                word.capitalize() for word in f"{presenter}_{signal}".split("_")
            )
            messages[f"{presenter}.{signal}"] = {
                "name": f"{presenter}.{signal}",
                "title": title_case,
                "contentType": "application/json",
                "payload": {
                    "title": title_case,
                    "type": "object",
                    "properties": {
                        "presenter": {"type": "string", "const": presenter},
                        "signal": {"type": "string", "const": signal},
                        "args": {
                            "type": "array",
                            "items": arguments,
                            "additionalItems": False,
                            "minItems": len(arguments),
                            "maxItems": len(arguments),
                        },
                    },
                    "required": ["presenter", "signal", "args"],
                    "additionalProperties": False,
                },
            }
    return {
        "asyncapi": "3.0.0",
        "info": {"title": title, "version": __version__},
        "channels": {
            "events": {
                "address": "/api/events",
                "messages": {
                    name: {"$ref": f"#/components/messages/{name}"} for name in messages
                },
            }
        },
        "operations": {
            "sendEvents": {
                "action": "send",
                "channel": {"$ref": "#/channels/events"},
                "messages": [
                    {"$ref": f"#/channels/events/messages/{name}"} for name in messages
                ],
            }
        },
        "components": {
            "messages": messages,
            "schemas": draft07(top.get("$defs", {})),
        },
    }


def draft07(schema: Any) -> Any:
    """Return *schema* with each tuple written the draft-07 way.

    JSON Schema 2020-12 lists a tuple's items in `prefixItems` and the rest in
    `items`; draft-07 lists them in `items` and the rest in `additionalItems`.
    """
    match schema:
        case list():
            return [draft07(s) for s in schema]
        case dict():
            out: dict[str, Any] = {}
            for key, value in schema.items():
                if key in DATA:
                    out[key] = value
                elif key in NAMED:
                    out[key] = {name: draft07(s) for name, s in value.items()}
                else:
                    out[key] = draft07(value)
            if "prefixItems" in out:
                out["additionalItems"] = out.pop("items", False)
                out["items"] = out.pop("prefixItems")
            return out
    return schema
