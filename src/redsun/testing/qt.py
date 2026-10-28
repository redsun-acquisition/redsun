"""Pytest fixtures for testing Qt components.

A suite loads them with `-p redsun.testing.qt`, together with `-p redsun.testing`,
which provides the `no_automatic_collection` fixture they need. Loading them
makes a test using `qapp` that leaves the application's stylesheet, style, font
or palette changed fail, and releases the slots of the widgets freed after each
test module. On Windows under Qt's `offscreen` platform, they also point Qt at
the system fonts, which that platform otherwise lacks.

The `qapp` here gives way to another plugin's, such as `pytest-qt`'s, without
losing the delivery of emissions queued for the main thread.
"""

from __future__ import annotations

import gc
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from psygnal.qt import start_emitting_from_queue
from qtpy.QtCore import QCoreApplication, Qt
from qtpy.QtGui import QPalette
from qtpy.QtWidgets import QApplication

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = [
    "application_state",
    "emit_queued_on_main_thread",
    "keep_application_as_found",
    "qapp",
    "release_slots_after_module",
]


def pytest_configure(config: pytest.Config) -> None:
    """Give Qt's `offscreen` platform the system fonts on Windows.

    There it finds no fonts of its own, so once an icon font is loaded every
    text falls back to it and measures nothing.
    """
    offscreen = os.environ.get("QT_QPA_PLATFORM", "").startswith("offscreen")
    if offscreen and sys.platform == "win32":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        os.environ.setdefault("QT_QPA_FONTDIR", str(fonts))


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Return the one `QApplication` of the whole run."""
    return cast("QApplication", QApplication.instance() or QApplication([]))


@pytest.fixture(autouse=True)
def emit_queued_on_main_thread(request: pytest.FixtureRequest) -> None:
    """Deliver the `psygnal` emissions queued for the main thread to a test using `qapp`.

    It asks for `qapp` by name, so whichever plugin supplies it, this one's or
    another's, has made the application before the delivery starts.
    """
    if "qapp" in request.fixturenames:
        request.getfixturevalue("qapp")
        start_emitting_from_queue()


@pytest.fixture(scope="module", autouse=True)
def release_slots_after_module(
    no_automatic_collection: None,
) -> Generator[None, None, None]:
    """Collect after the last test of each module, then release the slots of the widgets freed."""
    yield
    gc.collect()
    # pyqt6 holds each slot of a deleted widget until two passes run
    QCoreApplication.sendPostedEvents()
    QCoreApplication.sendPostedEvents()


def application_state(app: QApplication) -> tuple[str, str, str, QPalette | None]:
    """Return *app*'s stylesheet, style name and font, and its palette if one was set by hand.

    A palette nobody set follows the style and the colour scheme, so it is
    left out.
    """
    style = app.style()
    by_hand = app.testAttribute(Qt.ApplicationAttribute.AA_SetPalette)
    return (
        app.styleSheet(),
        style.objectName() if style is not None else "",
        app.font().toString(),
        app.palette() if by_hand else None,
    )


@pytest.fixture(autouse=True)
def keep_application_as_found(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Fail a test using `qapp` that left the application's stylesheet, style, font or palette changed.

    A hook provider undoes in `shutdown` what it changed on the application,
    and a test that changes it by hand puts it back. A test that does not ask
    for the `qapp` fixture is not checked.

    Raises
    ------
    RuntimeError
        If one of them differs after the test from before it; the
        stylesheet and the palette are put back first, so they do not style
        the tests after this one.
    """
    if "qapp" not in request.fixturenames:
        yield
        return
    app: QApplication = request.getfixturevalue("qapp")
    before = application_state(app)
    yield
    after = application_state(app)
    if after == before:
        return
    app.setStyleSheet(before[0])
    app.setPalette(before[3] if before[3] is not None else QPalette())
    names = ("stylesheet", "style", "font", "palette")
    changed = [
        name for name, was, now in zip(names, before, after, strict=True) if was != now
    ]
    raise RuntimeError(
        f"this test left the application changed ({', '.join(changed)}); a hook "
        "provider undoes its work in shutdown, and a test that changes the "
        "application puts it back"
    )
