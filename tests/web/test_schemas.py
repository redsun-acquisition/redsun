"""Tests for the JSON Schema checks of what a presenter serves."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import pytest
from psygnal import Signal

from redsun import AsPresenter, BuildError, remote, slot
from redsun.fastapi import FastAPISession
from redsun.fastapi._schemas import signal_adapters, signal_schema
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


class WithPlain(FastAPISession):
    taking: AsPresenter[TakesPlain]
    untyped: AsPresenter[Untyped]


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
        signal_adapters(presenter, serving, {})


def test_an_object_argument_is_published_untyped() -> None:
    """Describe an object-typed signal argument with an empty schema."""
    presenter = Untyped()
    serving = served(presenter)
    assert serving is not None
    schema = signal_schema(signal_adapters(presenter, serving, {}))
    assert schema["sig_any"] == [{"type": "string"}, {}]


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
