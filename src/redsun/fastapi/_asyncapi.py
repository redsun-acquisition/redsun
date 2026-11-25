"""The objects of an AsyncAPI 3.0.0 document, as far as the event socket uses them."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Reference(BaseModel):
    """A pointer to an object elsewhere in the document."""

    ref: str = Field(serialization_alias="$ref")
    """The JSON Pointer of the object, such as `#/channels/events`."""


class Info(BaseModel):
    """What the document describes."""

    title: str
    """The application's name."""

    version: str
    """The application's version."""


class Channel(BaseModel):
    """Where messages travel, and which ones."""

    address: str
    """The path of the socket."""

    messages: dict[str, Reference]
    """The messages sent on it, by name."""


class Operation(BaseModel):
    """What the application does on a channel."""

    action: Literal["send"]
    """The application sends the messages."""

    channel: Reference
    """The channel it acts on."""

    messages: list[Reference]
    """The messages of the channel the operation covers."""


class Message(BaseModel):
    """One kind of message, and the schema of its payload."""

    name: str
    """The message's name."""

    title: str
    """A readable name, which code generators name the payload's type after."""

    content_type: str = Field(serialization_alias="contentType")
    """The media type of the payload."""

    payload: dict[str, Any]
    """The JSON Schema of the payload."""


class Components(BaseModel):
    """The objects the rest of the document refers to."""

    messages: dict[str, Message]
    """Every message, by name."""

    schemas: dict[str, Any]
    """The JSON Schema of every type a payload refers to, by name."""


class Document(BaseModel):
    """An AsyncAPI 3.0.0 document."""

    asyncapi: Literal["3.0.0"] = "3.0.0"
    """The version of the specification the document follows."""

    info: Info
    """What the document describes."""

    channels: dict[str, Channel]
    """Every channel, by name."""

    operations: dict[str, Operation]
    """Every operation, by name."""

    components: Components
    """The objects the rest of the document refers to."""
