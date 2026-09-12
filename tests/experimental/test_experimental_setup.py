"""Components take what another component owns in `setup`, once all exist."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, NewType

import pytest
from psygnal import Signal

from redsun.experimental import (
    AsPresenter,
    AsView,
    Placement,
    Session,
    provides,
    slot,
)

if TYPE_CHECKING:
    from .conftest import BuildSession

Readings = NewType("Readings", "dict[str, float]")
Absent = NewType("Absent", str)


@dataclass(frozen=True)
class Somewhere(Placement):
    """Stand-in placement: the core ships none, and no frontend is named here."""


class Sharing:
    """Presenter sharing a value, declared below the one that wants it."""

    def __init__(self, name: str, /) -> None:
        self.name = name

    @provides
    def readings(self) -> Readings:
        return Readings({"stage": 1.0})


class Taking:
    """Presenter taking that value once every component exists."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.readings: Readings | None = None

    def setup(self, readings: Readings) -> None:
        self.readings = readings


class Failing:
    """Its `setup` raises, so what it would have assigned is missing."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.ready = False

    def setup(self, readings: Readings) -> None:
        raise RuntimeError("no readings")


class Unplugged:
    """Presenter that cannot be built, so what it shares never arrives."""

    def __init__(self, name: str, /) -> None:
        raise RuntimeError("unplugged")

    @provides
    def readings(self) -> Readings:
        return Readings({})


class Asking:
    """Its `setup` asks for something nothing in the session declares."""

    def __init__(self, name: str, /) -> None:
        self.name = name

    def setup(self, missing: Absent) -> None: ...


class Awaiting:
    """Its `setup` is a coroutine, which the session would never await."""

    def __init__(self, name: str, /) -> None:
        self.name = name

    async def setup(self, readings: Readings) -> None: ...


class Listening:
    """Presenter a view may both hold and publish to."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.refreshed = 0.0

    @provides
    def readings(self) -> Readings:
        return Readings({"stage": 1.0})

    @slot
    def refresh(self, amount: float) -> None:
        self.refreshed = amount


class Calling:
    """A view holding its presenter and publishing to it as well."""

    sig_moved = Signal(float)
    placement: Placement = Somewhere()

    def __init__(self, name: str, /, presenter: Listening) -> None:
        self.name = name
        self.presenter = presenter


class SetUpApp(Session):
    taking: AsPresenter[Taking]
    sharing: AsPresenter[Sharing]


class FailingApp(Session):
    failing: AsPresenter[Failing]
    sharing: AsPresenter[Sharing]


class UnpluggedApp(Session):
    taking: AsPresenter[Taking]
    broken: AsPresenter[Unplugged]


class AskingApp(Session):
    asking: AsPresenter[Asking]


class AwaitingApp(Session):
    awaiting: AsPresenter[Awaiting]


class DoubleRouteApp(Session):
    listening: AsPresenter[Listening]
    panel: AsView[Calling]

    def wire(self) -> None:
        self.connect(self.panel.sig_moved, self.listening.refresh)


def test_setup_takes_a_value_shared_by_a_component_declared_below_it(
    build: BuildSession,
) -> None:
    """Every component exists by then, so declaration order does not matter."""
    app = build(SetUpApp)
    assert app.taking.readings == {"stage": 1.0}


def test_a_setup_that_raises_leaves_the_component_in_place(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """What its constructor built still works; what `setup` assigns is missing."""
    with caplog.at_level(logging.WARNING, logger="redsun"):
        app = build(FailingApp)

    assert set(app.presenters) == {"failing", "sharing"}
    assert app.failing.ready is False
    assert "Failed to set up presenter 'failing': no readings" in caplog.text
    assert "Not set up: failing (presenter)" in caplog.text


def test_a_setup_wanting_a_component_that_failed_is_not_called(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    with caplog.at_level(logging.WARNING, logger="redsun"):
        app = build(UnpluggedApp)

    assert app.taking.readings is None
    assert "Failed to set up presenter 'taking': 'broken' was not built" in caplog.text


def test_a_setup_asking_for_what_nothing_declares_is_refused() -> None:
    with pytest.raises(TypeError, match=r"'asking.setup' asks for 'missing'"):
        AskingApp().build()


def test_an_async_setup_is_refused_at_declaration() -> None:
    with pytest.raises(TypeError, match="must be synchronous"):
        AwaitingApp().build()


def test_a_component_reaching_another_two_ways_is_named(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """An action written both ways runs twice, and nothing else says so."""
    with caplog.at_level(logging.WARNING, logger="redsun"):
        build(DoubleRouteApp)

    assert "'panel' holds 'listening' and is also connected to it" in caplog.text
