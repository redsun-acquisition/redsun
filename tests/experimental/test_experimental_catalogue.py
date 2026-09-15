"""The session collects its document routers into a catalogue a component asks for."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, NewType, TypeAlias

import pytest
from event_model import DocumentRouter
from event_model.documents import Document

from redsun.experimental import (
    AsPresenter,
    AsView,
    CallbackType,
    Placement,
    Session,
    provides,
)

if TYPE_CHECKING:
    from .conftest import BuildSession


Gain = NewType("Gain", float)

SpelledOutCallback: TypeAlias = Callable[[str, Document], None] | DocumentRouter


@dataclass(frozen=True)
class Panel(Placement):
    side: str


class Listener:
    """Presenter asking for every router the session built."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.callbacks: Mapping[str, CallbackType] = {}

    def setup(self, callbacks: Mapping[str, CallbackType]) -> None:
        self.callbacks = callbacks


class SpelledOutListener:
    """Presenter asking for the catalogue without importing `CallbackType`."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.callbacks: Mapping[str, SpelledOutCallback] = {}

    def setup(self, callbacks: Mapping[str, SpelledOutCallback]) -> None:
        self.callbacks = callbacks


class Plain(DocumentRouter):
    """Router asking for nothing and sharing nothing."""

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name


class Sharing(DocumentRouter):
    """Router sharing a value another router is built from."""

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name

    @provides
    def gain(self) -> Gain:
        return Gain(2.0)


class Needing(DocumentRouter):
    """Router built from what `Sharing` shares."""

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name
        self.gain = Gain(0.0)

    def setup(self, gain: Gain) -> None:
        self.gain = gain


class Curious(DocumentRouter):
    """Router asking for the catalogue it is itself part of."""

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name
        self.callbacks: Mapping[str, CallbackType] = {}

    def setup(self, callbacks: Mapping[str, CallbackType]) -> None:
        self.callbacks = callbacks


class Broken(DocumentRouter):
    """Router whose constructor raises."""

    def __init__(self, name: str, /) -> None:
        raise RuntimeError("unplugged")


class RoutingView(DocumentRouter):
    """View that is also a router."""

    placement: Placement = Panel("left")

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name


class DeclaredAboveTheRouters(Session):
    listener: AsPresenter[Listener]
    first: AsPresenter[Needing]
    second: AsPresenter[Sharing]


class SpelledOutAboveTheRouters(Session):
    listener: AsPresenter[SpelledOutListener]
    first: AsPresenter[Needing]
    second: AsPresenter[Sharing]


class WithAPlainRouter(Session):
    listener: AsPresenter[Listener]
    plain: AsPresenter[Plain]


class WithABrokenRouter(Session):
    listener: AsPresenter[Listener]
    broken: AsPresenter[Broken]
    plain: AsPresenter[Plain]


class WithACuriousRouter(Session):
    curious: AsPresenter[Curious]
    plain: AsPresenter[Plain]


class ListeningToAView(Session):
    listener: AsPresenter[Listener]
    display: AsView[RoutingView]


def test_the_catalogue_holds_every_router_in_declaration_order(
    build: BuildSession,
) -> None:
    """`second` is built before `first`, and both before the listener."""
    app = build(DeclaredAboveTheRouters)
    assert list(app.listener.callbacks.items()) == [
        ("first", app.first),
        ("second", app.second),
    ]


def test_a_listener_writing_the_type_out_receives_the_same_catalogue(
    build: BuildSession,
) -> None:
    """Without importing `CallbackType`, it is ordered and answered the same way."""
    app = build(SpelledOutAboveTheRouters)
    assert list(app.listener.callbacks.items()) == [
        ("first", app.first),
        ("second", app.second),
    ]


def test_a_router_that_fails_to_build_is_absent(build: BuildSession) -> None:
    """The listener still builds, with the routers that did."""
    app = build(WithABrokenRouter)
    assert list(app.listener.callbacks) == ["plain"]


def test_a_router_asking_for_the_catalogue_is_in_it(build: BuildSession) -> None:
    """Every router exists before any setup runs, the asker included."""
    app = build(WithACuriousRouter)
    assert dict(app.curious.callbacks) == {"curious": app.curious, "plain": app.plain}


def test_a_router_in_the_catalogue_is_not_reported_unused(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    with caplog.at_level(logging.WARNING, logger="redsun"):
        build(WithAPlainRouter)
    assert "'plain' shares nothing" not in caplog.text


def test_a_presenter_asking_for_a_view_router_is_refused() -> None:
    """The view is built after the presenter, so its catalogue would lack it."""
    with pytest.raises(TypeError, match="'display', which is a view"):
        ListeningToAView().build()
