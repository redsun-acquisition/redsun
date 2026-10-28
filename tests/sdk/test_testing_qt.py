"""The fixtures `redsun.testing.qt` gives a suite testing Qt components."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from redsun.testing.qt import application_state

if TYPE_CHECKING:
    from qtpy.QtWidgets import QApplication

pytest_plugins = ["pytester"]

THE_SUITES_QAPP = """
import pytest
from qtpy.QtWidgets import QApplication


@pytest.fixture
def qapp():
    return QApplication.instance()
"""
"""A `qapp` fixture handing out the application the outer run holds."""

STYLES_THE_APPLICATION = """
def test_styles_the_application(qapp):
    qapp.setStyleSheet("QLabel { color: red; }")


def test_after(qapp):
    assert qapp.styleSheet() == ""
"""
"""Two tests, the first leaving a stylesheet on the application."""

COLOURS_THE_APPLICATION = """
from qtpy.QtGui import QColor, QPalette


def test_colours_the_application(qapp):
    palette = qapp.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("red"))
    qapp.setPalette(palette)


def test_after(qapp):
    assert qapp.palette().color(QPalette.ColorRole.Window) != QColor("red")
"""
"""Two tests, the first leaving a palette set by hand on the application."""

ANOTHER_QAPP = """
import pytest
from qtpy.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])
"""
"""A `qapp` that makes the application and nothing else, as `pytest-qt`'s does."""

QUEUED_EMISSION = """
import threading
import time

from psygnal import Signal
from qtpy.QtCore import QCoreApplication


class Source:
    sig_value = Signal(int)


def test_a_queued_emission_arrives(qapp):
    source = Source()
    received = []
    source.sig_value.connect(received.append, thread=threading.main_thread())
    worker = threading.Thread(target=lambda: source.sig_value.emit(1))
    worker.start()
    worker.join()
    deadline = time.monotonic() + 5
    while not received and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert received == [1]
"""
"""One test waiting for a value emitted on a worker thread to reach the main thread."""

NO_QAPP = """
from qtpy.QtWidgets import QApplication


def test_no_application_is_made():
    assert QApplication.instance() is None
"""
"""One test not using `qapp`, checking that no application exists."""

NO_QT = """
import sys


def test_qt_is_not_imported():
    assert "qtpy" not in sys.modules
"""
"""One test checking that nothing in the run imported `qtpy`."""

SLOTS_CONFTEST = """
import pytest


@pytest.fixture(scope="session")
def slots():
    return []
"""
"""A list the two modules below share, holding a weakref to a slot."""

FREES_A_RECEIVER = """
import weakref

from qtpy.QtWidgets import QPushButton


def receiver_class():
    class Receiver:
        def __init__(self):
            self.me = self
            self.button = QPushButton()
            self.button.clicked.connect(self.on_clicked)

        def on_clicked(self):
            pass

    return Receiver


def test_connect_a_receiver_only_a_cycle_holds(qapp, slots):
    receiver = receiver_class()
    slots.append(weakref.ref(receiver.on_clicked))
    receiver()
"""
"""A module leaving a widget and its slot in a cycle for the module-end collection."""

CHECKS_THE_SLOT = """
def test_the_slot_was_released(slots):
    assert slots[0]() is None
"""
"""A later module checking that the slot left behind is gone."""


@pytest.mark.qt
@pytest.mark.parametrize(
    ("source", "test"),
    [
        (STYLES_THE_APPLICATION, "test_styles_the_application"),
        (COLOURS_THE_APPLICATION, "test_colours_the_application"),
    ],
    ids=["stylesheet", "palette"],
)
def test_a_test_leaving_the_application_changed_is_refused(
    qapp: QApplication, pytester: pytest.Pytester, source: str, test: str
) -> None:
    """Fail the test that left the application's stylesheet or palette changed, and put it back."""
    before = application_state(qapp)
    pytester.makeconftest(THE_SUITES_QAPP)
    pytester.makepyfile(source)

    result = pytester.runpytest("-p", "redsun.testing", "-p", "redsun.testing.qt")

    result.assert_outcomes(passed=2, errors=1)
    result.stdout.fnmatch_lines(["*left the application changed*", f"ERROR *::{test}*"])
    assert application_state(qapp) == before


@pytest.mark.qt
def test_the_slots_of_widgets_freed_after_a_module_are_released(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Release the slots of the widgets the collection after a module frees, before the next module runs."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytester.makeconftest(SLOTS_CONFTEST)
    pytester.makepyfile(
        test_a_frees_a_receiver=FREES_A_RECEIVER,
        test_b_checks_the_slot=CHECKS_THE_SLOT,
    )

    result = pytester.runpytest_subprocess(
        "-p", "redsun.testing", "-p", "redsun.testing.qt"
    )

    result.assert_outcomes(passed=2)


@pytest.mark.qt
def test_a_queued_emission_arrives_with_another_qapp(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deliver a queued emission on the main thread when another plugin's `qapp` supplies the application."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytester.makeconftest(ANOTHER_QAPP)
    pytester.makepyfile(QUEUED_EMISSION)

    result = pytester.runpytest_subprocess(
        "-p", "redsun.testing", "-p", "redsun.testing.qt"
    )

    result.assert_outcomes(passed=1)


@pytest.mark.qt
def test_a_test_without_qapp_leaves_the_application_alone(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Make no application for a test that does not use `qapp`."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytester.makepyfile(NO_QAPP)

    result = pytester.runpytest_subprocess(
        "-p", "redsun.testing", "-p", "redsun.testing.qt"
    )

    result.assert_outcomes(passed=1)


def test_the_core_plugin_never_imports_qt(pytester: pytest.Pytester) -> None:
    """Run a suite loading only `redsun.testing` without importing `qtpy`."""
    pytester.makepyfile(NO_QT)

    result = pytester.runpytest_subprocess("-p", "redsun.testing")

    result.assert_outcomes(passed=1)
