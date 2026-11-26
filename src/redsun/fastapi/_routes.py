"""The routes publishing a session's presenters."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any

import anyio
from fastapi import APIRouter, Body, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel
from pydantic_core import PydanticSerializationError
from starlette.exceptions import HTTPException

from ..ports._remote import served
from ._schemas import asyncapi_document, check_schemas

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Mapping, MutableMapping

    from anyio.streams.memory import (
        MemoryObjectReceiveStream,
        MemoryObjectSendStream,
    )
    from fastapi import FastAPI, Response
    from pydantic import TypeAdapter

    from ..ports._remote import Command, Query, Served
    from ._schemas import Adapters

EVENT_BUFFER = 1000
"""Messages one socket holds before newer ones are dropped for it."""

Message = dict[str, object]

logger = logging.getLogger("redsun")


def build_api(
    app: FastAPI,
    presenters: Mapping[str, object],
    refused: MutableMapping[str, BaseException],
) -> list[Callable[[], None]]:
    """Add to *app* the routes of every presenter with a remote member.

    Their signals are sent on the WebSocket `/api/events`, which the AsyncAPI
    document at `GET /asyncapi.json` describes. A presenter whose routes cannot
    be built, for breaking a rule of `served`, serving a type with no JSON
    Schema or any other reason, is left out, logged and recorded in *refused*
    under its name. The callables returned disconnect what the API connected
    and close the sockets still open.
    """
    listeners: set[Listener] = set()
    releases: list[Callable[[], None]] = [partial(close_all, listeners)]
    signals: dict[str, dict[str, list[TypeAdapter[Any]]]] = {}
    operations: set[str] = set()
    adapters: Adapters = {}
    for name, presenter in presenters.items():
        try:
            serving = served(presenter)
            if serving is None:
                continue
            arguments = check_schemas(presenter, serving, adapters)
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
        signals[name] = arguments
        for signal_name, signal in serving.signals.items():
            relay = relay_for(listeners, name, signal_name, arguments[signal_name])
            signal.connect(relay)
            releases.append(partial(signal.disconnect, relay))

    app.state.asyncapi = asyncapi_document(app.title, signals)
    app.state.listeners = listeners
    app.add_api_route(
        "/asyncapi.json", asyncapi, methods=["GET"], operation_id="get_asyncapi"
    )
    app.add_api_websocket_route("/api/events", events)
    return releases


# Request is imported at runtime: FastAPI reads this annotation to pass the request
async def asyncapi(request: Request) -> dict[str, Any]:
    """Return the AsyncAPI document of the app's event socket."""
    document: dict[str, Any] = request.app.state.asyncapi
    return document


# WebSocket is imported at runtime: FastAPI reads this annotation to pass the socket
async def events(websocket: WebSocket) -> None:
    """Send the client every emission of a served signal, until it leaves."""
    await relay_events(websocket, websocket.app.state.listeners)


def routes_of(presenter: str, serving: Served, operations: set[str]) -> APIRouter:
    """Return the routes of *presenter*, and add their operation ids to *operations*.

    Raises
    ------
    TypeError
        Listing every route that cannot be served: two remote slots on one
        port, a parameter a request body cannot carry, or an operation id
        another presenter took.
    """
    counted = Counter(command.name for command in serving.commands)
    problems = [
        f"two remote slots answer to the port {port!r}"
        for port, count in counted.items()
        if count > 1
    ]
    # FastAPI's own errors for these names do not say which parameter is wrong
    problems.extend(
        f"{command.name!r} has a parameter {p!r}, which a request body cannot "
        "carry: it starts with '_' or is a name pydantic models use"
        for command in serving.commands
        for p in command.parameters
        if p.startswith("_") or hasattr(BaseModel, p)
    )
    if problems:
        raise TypeError("\n".join(f"- {p}" for p in problems))
    router = APIRouter(
        tags=[presenter],
        generate_unique_id_function=operation_id,
        route_class=RemoteRoute,
    )
    for command in serving.commands:
        add_command(router, presenter, command)
    for query in serving.queries:
        add_query(router, presenter, query)
    ids = [route.unique_id for route in router.routes if isinstance(route, APIRoute)]
    taken = [
        f"- the operation id {i!r} is taken by another presenter"
        for i in ids
        if i in operations
    ]
    if taken:
        raise TypeError("\n".join(taken))
    operations.update(ids)
    return router


def operation_id(route: APIRoute) -> str:
    """Return `{presenter}__{name}` for a command, `get_{presenter}__{name}` for a query."""
    prefix = "get_" if route.methods == {"GET"} else ""
    return f"{prefix}{route.tags[0]}__{route.name}"


def add_command(router: APIRouter, presenter: str, command: Command) -> None:
    """Add the POST route calling *command* with the body's fields."""

    async def endpoint(**kwargs: Any) -> object:
        return await command.call(**kwargs)

    signature = inspect.signature(command.call)
    # FastAPI builds the body from the endpoint's signature, which is the slot's own
    endpoint.__signature__ = signature.replace(  # type: ignore[attr-defined]
        parameters=[
            p.replace(
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[command.parameters[p.name], Body(embed=True)],
            )
            for p in signature.parameters.values()
        ],
        return_annotation=command.returns,
    )
    router.add_api_route(
        f"/api/{presenter}/{command.name}",
        endpoint,
        methods=["POST"],
        name=command.name,
    )


def add_query(router: APIRouter, presenter: str, query: Query) -> None:
    """Add the GET route reading *query*."""

    async def endpoint() -> object:
        return query.read()

    endpoint.__signature__ = inspect.Signature(return_annotation=query.returns)  # type: ignore[attr-defined]
    router.add_api_route(
        f"/api/{presenter}/{query.name}", endpoint, methods=["GET"], name=query.name
    )


class RemoteRoute(APIRoute):
    """A route of a presenter, answering 500 with the error's text when its member raises."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Return FastAPI's handler, with a failure of the member logged and answered."""
        handler = super().get_route_handler()

        async def answer(request: Request) -> Response:
            try:
                return await handler(request)
            except (HTTPException, RequestValidationError):
                raise
            # an app-wide Exception handler runs outside CORS and Starlette re-raises after it
            except Exception as error:
                logger.exception("Remote call %s.%s failed", self.tags[0], self.name)
                return JSONResponse({"error": str(error)}, 500)

        return answer


def relay_for(
    listeners: set[Listener],
    presenter: str,
    signal: str,
    adapters: list[TypeAdapter[Any]],
) -> Callable[..., None]:
    """Return a callback handing an emission of *signal* to every open socket.

    A signal is emitted on any thread, and a socket is written only from the
    loop serving it, so each message is passed to that loop, which adds it to
    the socket's stream. Nothing is done while no socket is open. An emission
    that cannot be serialised is logged and dropped.
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
        for listener in tuple(listeners):
            listener.hand_over(message)

    return relay


async def relay_events(websocket: WebSocket, listeners: set[Listener]) -> None:
    """Send *websocket* every message handed to it, until the client leaves.

    The listener is added before the socket is accepted, so a call the client
    makes once connected cannot emit before it.
    """
    send, receive = anyio.create_memory_object_stream[Message](EVENT_BUFFER)
    client = websocket.client
    listener = Listener(
        asyncio.get_running_loop(),
        send,
        f"{client.host}:{client.port}" if client else "unknown",
    )
    with send, receive:
        listeners.add(listener)
        try:
            await websocket.accept()
            sending = asyncio.ensure_future(send_received(websocket, receive))
            try:
                while (await websocket.receive())["type"] != "websocket.disconnect":
                    pass
            finally:
                sending.cancel()
                await asyncio.gather(sending, return_exceptions=True)
        finally:
            listeners.discard(listener)


async def send_received(
    websocket: WebSocket, receive: MemoryObjectReceiveStream[Message]
) -> None:
    """Send each message of *receive*, and close *websocket* once the stream is closed."""
    async for message in receive:
        await websocket.send_json(message)
    await websocket.close()


@dataclass(eq=False, slots=True)
class Listener:
    """An open event socket: the loop writing it and the stream of its messages."""

    loop: asyncio.AbstractEventLoop
    """The loop serving the socket."""

    stream: MemoryObjectSendStream[Message]
    """The messages waiting to be sent, `EVENT_BUFFER` at most."""

    client: str
    """The client's address, for the log."""

    full: bool = False
    """Whether a message was dropped since the stream was last under half full."""

    def hand_over(self, message: Message) -> None:
        """Pass *message* to the socket's loop, from any thread."""
        # a loop can close before its socket's handler drops the listener
        with suppress(RuntimeError):
            self.loop.call_soon_threadsafe(self.put, message)

    def put(self, message: Message) -> None:
        """Add *message* to the stream, or drop it while the stream is full.

        A warning is logged when the stream fills up, and again only after it
        has drained below half its size and filled up once more.
        """
        try:
            self.stream.send_nowait(message)
        except anyio.WouldBlock:
            if not self.full:
                logger.warning(
                    "Client %s of /api/events reads too slowly: %d events wait for "
                    "it, and newer ones are dropped until it takes some",
                    self.client,
                    EVENT_BUFFER,
                )
            self.full = True
        # the socket closed between the hand-over and now
        except (anyio.ClosedResourceError, anyio.BrokenResourceError):
            pass
        else:
            waiting = self.stream.statistics()
            if waiting.current_buffer_used < waiting.max_buffer_size / 2:
                self.full = False

    def close(self) -> None:
        """Close the stream from any thread, so the socket closes once it is sent."""
        with suppress(RuntimeError):
            self.loop.call_soon_threadsafe(self.stream.close)


def close_all(listeners: set[Listener]) -> None:
    """Close every open socket."""
    for listener in tuple(listeners):
        listener.close()
