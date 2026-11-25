"""Tests for the JSON Schema checks and the AsyncAPI document of what a presenter serves."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient
from psygnal import Signal
from pydantic import BaseModel

from redsun import AsPresenter, BuildError, remote, slot
from redsun.fastapi import FastAPISession
from redsun.fastapi._schemas import asyncapi_document, check_schemas
from redsun.ports._remote import served

if TYPE_CHECKING:
    from redsun.testing import BuildSession


class Plain:
    def __init__(self, x: int) -> None:
        self.x = x


class Untyped:
    sig_any = Signal(str, object)

    def __init__(self, name: str = "untyped") -> None:
        self.name = name

    @slot
    @remote
    async def go(self) -> None: ...


class TakesPlain:
    sig_taken = Signal(float)

    def __init__(self, name: str = "taking") -> None:
        self.name = name

    @slot
    @remote
    async def go(self, value: Plain) -> None: ...


class ReturnsPlain:
    @slot
    @remote
    async def go(self) -> Plain:
        return Plain(1)


class ReadsPlain:
    @property
    @remote
    def state(self) -> Plain:
        return Plain(1)


class EmitsPlain:
    sig_plain = Signal(Plain)

    @slot
    @remote
    async def go(self) -> None: ...


class Units(BaseModel):
    name: str
    scale: float


class Reading(BaseModel):
    value: float
    units: Units
    span: tuple[float, float]


class EmitsReading:
    sig_reading = Signal(str, Reading)

    @slot
    @remote
    async def go(self) -> None: ...


class WithPlain(FastAPISession):
    taking: AsPresenter[TakesPlain]
    untyped: AsPresenter[Untyped]


def walk(schema: Any) -> list[tuple[str, Any]]:
    """Return every key of *schema* with its value, at any depth."""
    match schema:
        case dict():
            return [
                pair
                for key, value in schema.items()
                for pair in [(key, value), *walk(value)]
            ]
        case list():
            return [pair for item in schema for pair in walk(item)]
    return []


def document_of(presenter: object) -> dict[str, Any]:
    """Return the AsyncAPI document of *presenter* served alone, as `probe`."""
    serving = served(presenter)
    assert serving is not None
    return asyncapi_document("x", {"probe": check_schemas(presenter, serving, {})})


@pytest.mark.parametrize(
    ("cls", "message"),
    [
        (TakesPlain, "'go' takes a type with no JSON Schema (value)"),
        (ReturnsPlain, "'go' returns a type with no JSON Schema"),
        (ReadsPlain, "'state' returns a type with no JSON Schema"),
        (EmitsPlain, "signal 'sig_plain' has an argument type with no JSON Schema"),
    ],
)
def test_a_type_with_no_json_schema_is_refused(cls: type, message: str) -> None:
    """Refuse a parameter, return or signal argument type with no JSON Schema, naming the member."""
    presenter = cls()
    serving = served(presenter)
    assert serving is not None
    with pytest.raises(TypeError, match=re.escape(message)):
        check_schemas(presenter, serving, {})


def test_an_object_argument_is_published_untyped() -> None:
    """Describe an object-typed signal argument with an empty schema."""
    message = document_of(Untyped())["components"]["messages"]["probe.sig_any"]
    assert message["payload"]["properties"]["args"]["items"] == [
        {"type": "string"},
        {},
    ]


def test_nested_models_are_components_written_as_draft_07() -> None:
    """Put a signal's model and the model inside it in the components, with draft-07 tuples."""
    document = document_of(EmitsReading())
    schemas = document["components"]["schemas"]
    assert set(schemas) == {"Reading", "Units"}
    pairs = walk(document)
    refs = {value for key, value in pairs if key == "$ref"}
    assert {"#/components/schemas/Reading", "#/components/schemas/Units"} <= refs
    assert all(r.startswith(("#/components/", "#/channels/")) for r in refs)
    assert not [key for key, _ in pairs if key in {"$defs", "prefixItems"}]
    assert schemas["Reading"]["properties"]["span"]["items"] == [
        {"type": "number"},
        {"type": "number"},
    ]


def test_a_presenter_left_out_has_no_messages(build: BuildSession) -> None:
    """Leave the signals of a presenter left out of the API out of the AsyncAPI document."""
    session = build(WithPlain)
    with TestClient(session.app) as client:
        document = client.get("/asyncapi.json").json()
    assert list(document["components"]["messages"]) == ["untyped.sig_any"]


def test_a_presenter_serving_a_type_with_no_schema_is_left_out(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Leave out of the API a presenter serving a type with no JSON Schema, and serve the rest."""
    with caplog.at_level(logging.ERROR, logger="redsun"):
        session = build(WithPlain)
    paths = session.app.openapi()["paths"]
    assert "/api/taking/go" not in paths
    assert "/api/untyped/go" in paths
    assert "'go' takes a type with no JSON Schema (value)" in caplog.text


def test_a_strict_session_refuses_a_type_with_no_schema(build: BuildSession) -> None:
    """Raise at the report step of a strict session serving a type with no JSON Schema."""
    with pytest.raises(BuildError, match="taking"):
        build(WithPlain, {"strict": True})
