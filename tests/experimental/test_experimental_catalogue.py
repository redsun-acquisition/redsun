"""The session collects its document routers into a catalogue a component asks for."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, NewType

import pytest
from event_model import DocumentRouter

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


@dataclass(frozen=True)
class Panel(Placement):
    side: str


class Listener:
    """Presenter asking for every router the session built."""

    def __init__(self, name: str, /, callbacks: Mapping[str, CallbackType]) -> None:
        self.name = name
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

    def __init__(self, name: str, /, gain: Gain) -> None:
        super().__init__()
        self.name = name
        self.gain = gain


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


class WithAPlainRouter(Session):
    listener: AsPresenter[Listener]
    plain: AsPresenter[Plain]


class WithABrokenRouter(Session):
    listener: AsPresenter[Listener]
    broken: AsPresenter[Broken]
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


def test_a_router_that_fails_to_build_is_absent(build: BuildSession) -> None:
    """The listener still builds, with the routers that did."""
    app = build(WithABrokenRouter)
    assert list(app.listener.callbacks) == ["plain"]


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
