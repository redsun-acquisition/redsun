"""The routes publishing a session's presenters."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, WebSocket
from fastapi.responses import JSONResponse
from pydantic import BaseModel, create_model
from pydantic_core import PydanticSerializationError

from ..ports._remote import served
from ._schemas import signal_adapters, signal_schema

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, MutableMapping

    from fastapi import FastAPI
    from pydantic import TypeAdapter

    from ..ports._remote import Command, Query, Served
    from ._schemas import Adapters

Message = dict[str, object]
Listeners = dict[asyncio.Queue[Message | None], asyncio.AbstractEventLoop]

logger = logging.getLogger("redsun")


def build_api(
    app: FastAPI,
    presenters: Mapping[str, object],
    refused: MutableMapping[str, BaseException],
) -> list[Callable[[], None]]:
    """Add to *app* the routes of every presenter with a remote member.

    A presenter whose routes cannot be built, for breaking a rule of `served`,
    serving a type with no JSON Schema or any other reason, is left out,
    logged and recorded in *refused* under its name. The callables returned disconnect what the API connected and
    close the sockets still open.
    """
    listeners: Listeners = {}
    releases: list[Callable[[], None]] = [partial(close_all, listeners)]
    schemas: dict[str, dict[str, list[dict[str, Any]]]] = {}
    operations: set[str] = set()
    adapters: Adapters = {}
    for name, presenter in presenters.items():
        try:
            serving = served(presenter)
            if serving is None:
                continue
            arguments = signal_adapters(presenter, serving, adapters)
            router = routes_of(name, serving, operations)
        except TypeError as error:
            logger.error("Presenter '%s' is left out of the API: %s", name, error)
            refused[name] = error
            continue
        except Exception as error:
            logger.exception("Presenter '%s' is left out of the API", name)
            refused[name] = error
            continue
        app.include_router(router)
        schemas[name] = signal_schema(arguments)
        for signal_name, signal in serving.signals.items():
            relay = relay_for(listeners, name, signal_name, arguments[signal_name])
            signal.connect(relay)
            releases.append(partial(signal.disconnect, relay))

    async def signals() -> dict[str, dict[str, list[dict[str, Any]]]]:
        return schemas

    # WebSocket is imported at runtime: FastAPI reads this annotation to pass the socket
    async def events(websocket: WebSocket) -> None:
        await relay_events(websocket, listeners)

    app.add_api_route(
        "/api/signals", signals, methods=["GET"], operation_id="get_signals"
    )
    app.add_api_websocket_route("/api/events", events)
    return releases


def routes_of(presenter: str, serving: Served, operations: set[str]) -> APIRouter:
    """Return the routes of *presenter*, and add their operation ids to *operations*.

    Raises
    ------
    TypeError
        Listing every route that cannot be served: two remote slots on one
        port, a parameter a request body cannot carry, or an operation id
        another presenter took.
    """
    commands = [(c, f"{presenter}__{c.name}") for c in serving.commands]
    queries = [(q, f"get_{presenter}__{q.name}") for q in serving.queries]
    counted = Counter(command.name for command in serving.commands)
    problems = [
        f"two remote slots answer to the port {port!r}"
        for port, count in counted.items()
        if count > 1
    ]
    problems.extend(
        f"{command.name!r} has a parameter {p!r}, which a request body cannot "
        "carry: it starts with '_' or is a name pydantic models use"
        for command in serving.commands
        for p in command.parameters
        if p.startswith("_") or hasattr(BaseModel, p)
    )
    ids = [operation for _, operation in [*commands, *queries]]
    problems.extend(
        f"the operation id {i!r} is taken by another presenter"
        for i in ids
        if i in operations
    )
    if problems:
        raise TypeError("\n".join(f"- {p}" for p in problems))
    router = APIRouter()
    for command, operation in commands:
        add_command(router, presenter, command, operation)
    for query, operation in queries:
        add_query(router, presenter, query, operation)
    operations.update(ids)
    return router


def add_command(
    router: APIRouter, presenter: str, command: Command, operation: str
) -> None:
    """Add the POST route calling *command* with the body's fields."""

    async def endpoint(body: BaseModel) -> object:
        try:
            return await command.call(**body.model_dump())
        except Exception as error:
            logger.exception("Remote call %s.%s failed", presenter, command.name)
            return JSONResponse({"error": str(error)}, 500)

    fields: dict[str, Any] = {p: (t, ...) for p, t in command.parameters.items()}
    # the body type is the command's own, which no annotation written here can name
    endpoint.__annotations__["body"] = create_model(operation, **fields)
    router.add_api_route(
        f"/api/{presenter}/{command.name}",
        endpoint,
        methods=["POST"],
        response_model=command.returns,
        operation_id=operation,
    )


def add_query(router: APIRouter, presenter: str, query: Query, operation: str) -> None:
    """Add the GET route reading *query*."""

    async def endpoint() -> object:
        try:
            return query.read()
        except Exception as error:
            logger.exception("Remote read %s.%s failed", presenter, query.name)
            return JSONResponse({"error": str(error)}, 500)

    router.add_api_route(
        f"/api/{presenter}/{query.name}",
        endpoint,
        methods=["GET"],
        response_model=query.returns,
        operation_id=operation,
    )


def relay_for(
    listeners: Listeners,
    presenter: str,
    signal: str,
    adapters: list[TypeAdapter[Any]],
) -> Callable[..., None]:
    """Return a callback putting an emission of *signal* on every open socket's queue.

    Nothing is done while no socket is open. An emission that cannot be
    serialised is logged and dropped.
    """

    def relay(*args: object) -> None:
        if not listeners:
            return
        # an exception reaching the signal would fail the slot that emitted it
        try:
            values = [
                adapter.dump_python(value, mode="json")
                for adapter, value in zip(adapters, args, strict=False)
            ]
        except PydanticSerializationError as error:
            logger.warning("Signal %s.%s not sent: %s", presenter, signal, error)
            return
        message: Message = {"presenter": presenter, "signal": signal, "args": values}
        put_on_all(listeners, message)

    return relay


async def relay_events(websocket: WebSocket, listeners: Listeners) -> None:
    """Send *websocket* every message put on its queue, until the client leaves.

    The queue is listed before the socket is accepted, so a call the client
    makes once connected cannot emit before it.
    """
    queue: asyncio.Queue[Message | None] = asyncio.Queue()
    listeners[queue] = asyncio.get_running_loop()
    try:
        await websocket.accept()
        sending = asyncio.ensure_future(send_queued(websocket, queue))
        try:
            while (await websocket.receive())["type"] != "websocket.disconnect":
                pass
        finally:
            sending.cancel()
            await asyncio.gather(sending, return_exceptions=True)
    finally:
        del listeners[queue]


async def send_queued(
    websocket: WebSocket, queue: asyncio.Queue[Message | None]
) -> None:
    """Send each message of *queue*, and close *websocket* on `None`."""
    while (message := await queue.get()) is not None:
        await websocket.send_json(message)
    await websocket.close()


def put_on_all(listeners: Listeners, message: Message | None) -> None:
    """Put *message* on every open socket's queue, skipping a queue whose loop has closed."""
    for queue, loop in tuple(listeners.items()):
        # a loop can close before its socket's handler removes the queue
        with suppress(RuntimeError):
            loop.call_soon_threadsafe(queue.put_nowait, message)


def close_all(listeners: Listeners) -> None:
    """Close every open socket."""
    put_on_all(listeners, None)
