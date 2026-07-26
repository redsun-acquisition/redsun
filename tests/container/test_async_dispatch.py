"""End-to-end dispatch of a Qt view signal into a presenter coroutine slot."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, cast

import pytest
from mock_pkg.controller import AsyncMotorController
from mock_pkg.device import MyMotor
from mock_pkg.view import MockMotorView
from psygnal import get_async_backend

from redsun.aio import CulsansAsyncioBackend, get_shared_loop, run_coro
from redsun.containers.container import AppContainer
from redsun.containers.qt import QtAppContainer

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from qtpy.QtWidgets import QApplication

pytestmark = pytest.mark.qt

TIMEOUT = 5.0


def wait_until(predicate: Callable[[], bool], timeout: float = TIMEOUT) -> bool:
    """Poll ``predicate`` from the calling thread until it holds or time runs out."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


@pytest.fixture
def app(
    qapp: QApplication,
    mock_entry_points: Any,
    config_path: Path,
) -> Iterator[QtAppContainer]:
    """Boot a Qt container holding a view, a presenter and a mock motor."""
    container = cast(
        "QtAppContainer",
        AppContainer.from_config(str(config_path / "mock_async_config.yaml")),
    )
    container.build()
    container.connect_devices(mock=True)
    try:
        yield container
    finally:
        if container.is_built:
            container.shutdown()


def _view(app: QtAppContainer) -> MockMotorView:
    return cast("MockMotorView", app.views["motor_view"])


def _presenter(app: QtAppContainer) -> AsyncMotorController:
    return cast("AsyncMotorController", app.presenters["motor_controller"])


def test_container_boots_with_all_components(app: QtAppContainer) -> None:
    assert app.is_built
    assert isinstance(app.devices["my_motor"], MyMotor)
    assert isinstance(_presenter(app), AsyncMotorController)
    assert isinstance(_view(app), MockMotorView)


def test_build_installs_the_async_backend(app: QtAppContainer) -> None:
    backend = get_async_backend()
    assert isinstance(backend, CulsansAsyncioBackend)
    assert backend.running.is_set()


def test_view_signal_reaches_the_presenter_coroutine(app: QtAppContainer) -> None:
    view, presenter = _view(app), _presenter(app)

    view.move_button.click()

    assert wait_until(lambda: len(presenter.moves) == 1)
    assert presenter.moves == [("my_motor", 42.0)]
    # the slot ran on the shared loop, not on the Qt thread that emitted
    assert presenter.loops == [get_shared_loop()]


def test_coroutine_slot_drives_the_device(app: QtAppContainer) -> None:
    view, presenter = _view(app), _presenter(app)
    motor = cast("MyMotor", app.devices["my_motor"])

    view.position = 3.5
    view.move_button.click()

    assert wait_until(lambda: len(presenter.moves) == 1)
    assert run_coro(motor.floating.get_value()) == 3.5


def test_presenter_signal_travels_back_to_the_view_thread(
    app: QtAppContainer,
) -> None:
    view, presenter = _view(app), _presenter(app)
    received: list[tuple[str, float]] = []

    presenter.sig_motor_moved.connect(lambda m, p: received.append((m, p)))
    view.move_button.click()

    assert wait_until(lambda: len(received) == 1)
    assert received == [("my_motor", 42.0)]


def test_repeated_emissions_are_all_delivered(app: QtAppContainer) -> None:
    view, presenter = _view(app), _presenter(app)

    for position in (1.0, 2.0, 3.0):
        view.position = position
        view.move_button.click()

    assert wait_until(lambda: len(presenter.moves) == 3)
    assert sorted(p for _, p in presenter.moves) == [1.0, 2.0, 3.0]


def test_failing_slot_is_logged_and_does_not_break_dispatch(
    app: QtAppContainer, caplog: pytest.LogCaptureFixture
) -> None:
    view, presenter = _view(app), _presenter(app)

    with caplog.at_level(logging.ERROR, logger="redsun"):
        view.position = -1.0
        view.move_button.click()
        assert wait_until(lambda: "position out of range" in caplog.text)

    assert presenter.moves == []

    view.position = 7.0
    view.move_button.click()
    assert wait_until(lambda: presenter.moves == [("my_motor", 7.0)])


def test_shutdown_tears_down_presenter_and_backend(app: QtAppContainer) -> None:
    presenter = _presenter(app)
    backend = get_async_backend()
    assert isinstance(backend, CulsansAsyncioBackend)

    app.shutdown()

    assert presenter.shutdown_calls == 1
    assert not app.is_built
    assert get_async_backend() is None
    assert wait_until(lambda: not backend.running.is_set())


def test_rebuild_after_shutdown_reinstalls_the_backend(app: QtAppContainer) -> None:
    first = get_async_backend()
    app.shutdown()

    app.build()
    second = get_async_backend()

    assert isinstance(second, CulsansAsyncioBackend)
    assert second is not first
    assert second.running.is_set()
