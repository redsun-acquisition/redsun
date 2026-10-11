"""Tests for napari's look as a configure_application provider."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import pytest
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QGuiApplication

from redsun import AsHook, Declare
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


class LargeApp(QtSession):
    configure_application: Annotated[AsHook[NapariStyle], Declare(font_size=14)]


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


def test_the_font_size_sets_the_stylesheets_base_size(
    qapp: QApplication, build: BuildSession, unstyled: None
) -> None:
    """Fill napari's stylesheet from the font size given, the sizes derived from it included."""
    build(LargeApp)

    sheet = qapp.styleSheet()

    assert "font-size: 14pt;" in sheet
    assert "font-size: 15.0pt;" in sheet
    assert "font-size: 9pt;" not in sheet


@pytest.mark.parametrize("font_size", [0, -3, 9.5, "9", True])
def test_a_font_size_that_is_no_positive_whole_number_is_refused(
    font_size: object,
) -> None:
    """Refuse a font size that is not a positive whole number, naming it."""
    with pytest.raises(ValueError, match="font_size"):
        NapariStyle(font_size=font_size)  # type: ignore[arg-type]
