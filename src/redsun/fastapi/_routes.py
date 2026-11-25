"""The routes publishing a session's presenters."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from functools import partial
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket  # noqa: TC002
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, create_model
from pydantic_core import PydanticSerializationError

from ..ports._remote import served, signal_schema

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, MutableMapping

    from fastapi import FastAPI
    from pydantic import BaseModel

    from ..ports._remote import Command, Query, Served

Message = dict[str, object]
Listeners = dict[asyncio.Queue[Message | None], asyncio.AbstractEventLoop]

logger = logging.getLogger("redsun")


def build_api(
    app: FastAPI,
    presenters: Mapping[str, object],
    refused: MutableMapping[str, BaseException],
) -> list[Callable[[], None]]:
    """Add to *app* the routes of every presenter with a remote member.

    A presenter breaking a rule of `served` is left out, logged and recorded in
    *refused* under its name. The callables returned disconnect what the API
    connected and close the sockets still open.
    """
    listeners: Listeners = {}
    releases: list[Callable[[], None]] = [lambda: close_all(listeners)]
    schemas: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for name, presenter in presenters.items():
        try:
            serving = served(presenter)
            if serving is not None:
                refuse_shared_ports(serving)
        except TypeError as error:
            logger.error("Presenter '%s' is left out of the API: %s", name, error)
            refused[name] = error
            continue
        if serving is None:
            continue
        for command in serving.commands:
            add_command(app, name, command)
        for query in serving.queries:
            add_query(app, name, query)
        for signal_name, signal in serving.signals.items():
            relay = relay_for(
                listeners, name, signal_name, serving.signal_types[signal_name]
            )
            signal.connect(relay)
            releases.append(partial(signal.disconnect, relay))
        schemas[name] = signal_schema(serving)

    async def signals() -> dict[str, dict[str, list[dict[str, Any]]]]:
        return schemas

    # WebSocket is imported at runtime: FastAPI reads this annotation to pass the socket
    async def events(websocket: WebSocket) -> None:
        await relay_events(websocket, listeners)

    app.add_api_route("/api/signals", signals, methods=["GET"])
    app.add_api_websocket_route("/api/events", events)
    return releases


def refuse_shared_ports(serving: Served) -> None:
    """Refuse two remote slots answering to one port name, which one path cannot serve.

    Raises
    ------
    TypeError
        Naming each port name taken twice.
    """
    counted = Counter(command.name for command in serving.commands)
    shared = [name for name, count in counted.items() if count > 1]
    if shared:
        raise TypeError(
            "\n".join(f"- two remote slots answer to the port {n!r}" for n in shared)
        )


def add_command(app: FastAPI, presenter: str, command: Command) -> None:
    """Add the POST route calling *command* with the body's fields."""

    async def endpoint(body: BaseModel) -> object:
        try:
            return await command.call(**body.model_dump())
        except Exception as error:
            logger.exception("Remote call %s.%s failed", presenter, command.name)
            return JSONResponse({"error": str(error)}, 500)

    fields: dict[str, Any] = {p: (t, ...) for p, t in command.parameters.items()}
    # the body type is the command's own, which no annotation written here can name
    endpoint.__annotations__["body"] = create_model(
        f"{presenter}_{command.name}", **fields
    )
    app.add_api_route(
        f"/api/{presenter}/{command.name}",
        endpoint,
        methods=["POST"],
        response_model=command.returns,
    )


def add_query(app: FastAPI, presenter: str, query: Query) -> None:
    """Add the GET route reading *query*."""

    async def endpoint() -> object:
        try:
            return query.read()
        except Exception as error:
            logger.exception("Remote read %s.%s failed", presenter, query.name)
            return JSONResponse({"error": str(error)}, 500)

    app.add_api_route(
        f"/api/{presenter}/{query.name}",
        endpoint,
        methods=["GET"],
        response_model=query.returns,
    )


def relay_for(
    listeners: Listeners, presenter: str, signal: str, types: tuple[Any, ...]
) -> Callable[..., None]:
    """Return a callback putting an emission of *signal* on every open socket's queue.

    An emission that cannot be serialised is logged and dropped.
    """
    adapters = [TypeAdapter[Any](t) for t in types]

    def relay(*args: object) -> None:
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
        for queue, loop in tuple(listeners.items()):
            loop.call_soon_threadsafe(queue.put_nowait, message)

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


def close_all(listeners: Listeners) -> None:
    """Close every open socket."""
    for queue, loop in tuple(listeners.items()):
        loop.call_soon_threadsafe(queue.put_nowait, None)
