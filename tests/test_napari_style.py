"""Tests for napari's look as a configure_application provider."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QGuiApplication

from redsun import AsHook
from redsun.qt import QtSession
from redsun.qt.styles.napari import NapariStyle

if TYPE_CHECKING:
    from qtpy.QtWidgets import QApplication

    from redsun.testing import BuildSession

pytestmark = pytest.mark.qt

DARK_BACKGROUND = "rgb(35, 36, 43)"
LIGHT_BACKGROUND = "rgb(235, 231, 230)"


class StyledApp(QtSession):
    configure_application: AsHook[NapariStyle]


def images(sheet: str) -> list[Path]:
    """Return the image files a stylesheet names."""
    return [Path(url) for url in re.findall(r'url\("([^"]+)"\)', sheet)]


def test_the_session_takes_the_theme_of_the_colour_scheme(
    qapp: QApplication, build: BuildSession, unstyled: None
) -> None:
    """Apply napari's theme for the colour scheme in force, every image it names on disk."""
    build(StyledApp)
    hints = QGuiApplication.styleHints()
    assert hints is not None
    dark = hints.colorScheme() == QtNamespace.ColorScheme.Dark

    sheet = qapp.styleSheet()

    assert (DARK_BACKGROUND if dark else LIGHT_BACKGROUND) in sheet
    assert images(sheet)
    assert all(image.is_file() for image in images(sheet))


def test_a_scheme_change_switches_the_theme(
    qapp: QApplication, build: BuildSession, unstyled: None
) -> None:
    """Switch to napari's other theme and its images when the colour scheme changes."""
    build(StyledApp)
    hints = QGuiApplication.styleHints()
    assert hints is not None

    hints.colorSchemeChanged.emit(QtNamespace.ColorScheme.Dark)
    dark = qapp.styleSheet()
    hints.colorSchemeChanged.emit(QtNamespace.ColorScheme.Light)
    light = qapp.styleSheet()

    assert DARK_BACKGROUND in dark
    assert LIGHT_BACKGROUND in light
    assert all(image.is_file() for image in images(dark) + images(light))
    assert set(images(dark)).isdisjoint(images(light))


def test_shutdown_restores_the_stylesheet_and_stops_following(
    qapp: QApplication, build: BuildSession, unstyled: None
) -> None:
    """Restore the application's own stylesheet at shutdown, and ignore later scheme changes."""
    qapp.setStyleSheet("QLabel { color: red; }")
    hints = QGuiApplication.styleHints()
    assert hints is not None

    build(StyledApp).shutdown()
    hints.colorSchemeChanged.emit(QtNamespace.ColorScheme.Dark)

    assert qapp.styleSheet() == "QLabel { color: red; }"


def test_both_themes_icons_are_written_when_the_session_builds(
    qapp: QApplication, build: BuildSession, unstyled: None, tmp_path: Path
) -> None:
    """Write the icons of both themes at build, so a later scheme change writes no file."""
    build(StyledApp)

    written = [
        tmp_path / "napari-style" / name / "check.svg" for name in ("dark", "light")
    ]

    assert all(path.is_file() for path in written)
