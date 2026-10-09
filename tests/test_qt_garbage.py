"""Tests for where a Qt session collects Python's garbage."""

from __future__ import annotations

import gc
import threading
import weakref
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from qtpy.QtCore import QCoreApplication, QEvent, QTimer

from redsun.qt import QtSession

if TYPE_CHECKING:
    from collections.abc import Callable

    from qtpy.QtWidgets import QApplication

    from redsun.testing import BuildSession

pytestmark = pytest.mark.qt


class EmptyApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "garbage-session"}


class Cycle:
    """An object that refers to itself, so only the collector frees it."""

    def __init__(self) -> None:
        self.me = self


def test_a_cycle_is_collected_on_the_gui_thread(
    qapp: QApplication, build: BuildSession, wait_until: Callable[..., bool]
) -> None:
    """Collect a reference cycle on the GUI thread, with automatic collection off, while a session runs."""
    build(EmptyApp)
    freed: list[int] = []
    cycle = Cycle()
    weakref.finalize(cycle, lambda: freed.append(threading.get_ident()))
    del cycle
    automatic = gc.isenabled()
    # enough new objects for the first generation to pass its threshold
    junk: list[dict[str, int]] = [{} for _ in range(gc.get_threshold()[0] + 1)]

    assert wait_until(lambda: bool(freed))
    assert not automatic
    assert freed == [threading.main_thread().ident]
    del junk


@pytest.mark.parametrize("before", [True, False], ids=["on", "off"])
def test_shutdown_leaves_automatic_collection_as_it_found_it(
    qapp: QApplication, build: BuildSession, before: bool
) -> None:
    """Turn automatic collection back on at shutdown only if it was on before the build."""
    (gc.enable if before else gc.disable)()
    try:
        build(EmptyApp).shutdown()
        after = gc.isenabled()
    finally:
        gc.enable()

    assert after is before


def test_shutdown_frees_the_sessions_cycles_on_the_gui_thread(
    qapp: QApplication, build: BuildSession
) -> None:
    """Free the cycles left when a session shuts down, on the GUI thread, before collection is automatic again."""
    app = build(EmptyApp)
    freed: list[int] = []
    cycle = Cycle()
    weakref.finalize(cycle, lambda: freed.append(threading.get_ident()))
    del cycle

    app.shutdown()

    assert freed == [threading.main_thread().ident]


def test_shutdown_leaves_no_timer_behind(
    qapp: QApplication, build: BuildSession
) -> None:
    """Delete the collector's timer when the session shuts down."""
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    before = len(qapp.findChildren(QTimer))

    build(EmptyApp).shutdown()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    assert len(qapp.findChildren(QTimer)) == before
