"""Tests for qlementine's look as a configure_application provider."""

from __future__ import annotations

import json
import logging
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any

import pytest
from qtpy import API
from qtpy.QtCore import QPoint, QRect
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QColor, QFont, QGuiApplication, QPalette
from qtpy.QtWidgets import QToolButton, QWidget
from superqt import QCollapsible

from redsun import AsHook
from redsun.qt import QtHook, QtSession
from redsun.qt.styles import qlementine
from redsun.qt.styles.qlementine import QlementineStyle
from redsun.view.qt.icons import set_collapsible_icons, set_icon

if TYPE_CHECKING:
    from pathlib import Path

    from qtpy.QtWidgets import QApplication

    from redsun.testing import BuildSession

pytestmark = pytest.mark.qt

needs_qlementine = pytest.mark.skipif(
    find_spec(qlementine.MODULES[API]) is None,
    reason=f"needs the {qlementine.EXTRAS[API]} dependency group",
)


LAB_WINDOW = "#305070"
"""The window colour of the theme `lab_theme` writes."""


class StyledApp(QtSession):
    configure_application: AsHook[QlementineStyle]


class BareApp(QtSession):
    pass


@pytest.fixture
def lab_theme(tmp_path: Path) -> Path:
    """Return a theme file giving windows `LAB_WINDOW`, and the rest qlementine's defaults."""
    path = tmp_path / "lab.json"
    meta = {"name": "Lab", "author": "Lab", "version": "1.0"}
    path.write_text(json.dumps({"meta": meta, "backgroundColorMain2": LAB_WINDOW}))
    return path


def styled(build: BuildSession, **kwargs: object) -> QtSession:
    """Build a session whose file installs the style with *kwargs*."""
    hook = {"provider": "qlementine", "kwargs": kwargs}
    return build(BareApp, {"hooks": {"configure_application": hook}})


def window_colour(app: QApplication) -> QColor:
    """Return the colour the application's palette gives a window."""
    return app.palette().color(QPalette.ColorRole.Window)


def is_dark(app: QApplication) -> bool:
    """Tell whether the application's palette is a dark one."""
    return window_colour(app).lightness() < 128


def contrast(widget: QWidget, region: QRect | None = None) -> int:
    """Return how far apart the lightest and the darkest pixel of *widget* as drawn are, from 0 to 255, in *region* when given."""
    image = (widget.grab() if region is None else widget.grab(region)).toImage()
    lightness = [
        image.pixelColor(x, y).lightness()
        for x in range(image.width())
        for y in range(image.height())
    ]
    return max(lightness) - min(lightness)


def icon_region(button: QToolButton) -> QRect:
    """Return the square in the middle of *button* that its icon is drawn in, leaving the frame out."""
    region = QRect(QPoint(0, 0), button.iconSize())
    region.moveCenter(button.rect().center())
    return region


def style_name(app: QApplication) -> str:
    """Return the name of the application's style."""
    style = app.style()
    return style.objectName() if style is not None else ""


@needs_qlementine
def test_the_short_name_installs_the_style_in_the_theme_of_the_colour_scheme(
    qapp: QApplication, build: BuildSession
) -> None:
    """Install the style a session file names `qlementine`, in the theme of the colour scheme in force."""

    class App(QtSession):
        pass

    hints = QGuiApplication.styleHints()
    assert hints is not None
    dark = hints.colorScheme() == QtNamespace.ColorScheme.Dark

    build(App, {"hooks": {"configure_application": "qlementine"}})

    assert style_name(qapp) == "QlementineStyle"
    assert is_dark(qapp) is dark


@needs_qlementine
def test_a_scheme_change_switches_the_theme(
    qapp: QApplication, build: BuildSession
) -> None:
    """Switch between qlementine's dark and light themes when the colour scheme changes."""
    build(StyledApp)
    hints = QGuiApplication.styleHints()
    assert hints is not None

    hints.colorSchemeChanged.emit(QtNamespace.ColorScheme.Dark)
    dark = is_dark(qapp)
    hints.colorSchemeChanged.emit(QtNamespace.ColorScheme.Light)
    light = not is_dark(qapp)

    assert dark
    assert light


@needs_qlementine
@pytest.mark.parametrize(
    "scheme", [QtNamespace.ColorScheme.Dark, QtNamespace.ColorScheme.Light]
)
def test_an_icon_of_a_built_in_view_stands_out_in_each_theme(
    scheme: QtNamespace.ColorScheme, qapp: QApplication, build: BuildSession
) -> None:
    """Draw a font icon in a colour that stands out from its button, in the dark and the light theme."""
    build(StyledApp)
    hints = QGuiApplication.styleHints()
    assert hints is not None
    # the style is qlementine's own class; a change of theme is animated, and
    # a button drawn at once would show its old colours
    style: Any = qapp.style()
    style.setAnimationsEnabled(False)
    button = QToolButton()
    set_icon(button, "undo", "Undo the removal")
    button.resize(40, 40)

    hints.colorSchemeChanged.emit(scheme)
    qapp.processEvents()

    assert contrast(button, icon_region(button)) > 100


@needs_qlementine
@pytest.mark.parametrize(
    "scheme", [QtNamespace.ColorScheme.Dark, QtNamespace.ColorScheme.Light]
)
def test_the_header_of_a_collapsible_section_stands_out_in_each_theme(
    scheme: QtNamespace.ColorScheme, qapp: QApplication, build: BuildSession
) -> None:
    """Draw the header of a collapsible section in a colour that stands out, in the dark and the light theme."""
    build(StyledApp)
    hints = QGuiApplication.styleHints()
    assert hints is not None
    style: Any = qapp.style()
    style.setAnimationsEnabled(False)
    section = QCollapsible("Saved positions")
    set_collapsible_icons(section)

    hints.colorSchemeChanged.emit(scheme)
    qapp.processEvents()

    assert contrast(section.toggleButton()) > 100


@needs_qlementine
def test_shutdown_restores_the_style_under_a_stylesheet(
    qapp: QApplication, build: BuildSession
) -> None:
    """Put back the style of an application that has a stylesheet, which hides the style's name."""
    before = style_name(qapp)
    qapp.setStyleSheet("QLabel { color: red; }")
    try:
        build(StyledApp).shutdown()
    finally:
        qapp.setStyleSheet("")

    assert style_name(qapp) == before


@needs_qlementine
def test_a_theme_that_cannot_be_applied_leaves_the_application_as_it_was(
    qapp: QApplication, build: BuildSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Put back the style, font and palette when the style fails after it was set on the application."""

    def refuse(style: QlementineStyle, dark: bool) -> None:
        raise RuntimeError("the theme cannot be applied")

    monkeypatch.setattr(QlementineStyle, "_apply", refuse)
    before = (style_name(qapp), qapp.font().toString(), window_colour(qapp))

    session = build(StyledApp)

    assert session.hooks[QtHook.CONFIGURE_APPLICATION] == ()
    assert (style_name(qapp), qapp.font().toString(), window_colour(qapp)) == before


@needs_qlementine
def test_shutdown_gives_back_the_palette_of_the_platforms_style(
    qapp: QApplication, build: BuildSession
) -> None:
    """Give back the style's own palette at shutdown when the application had set none."""
    before = window_colour(qapp)
    session = build(StyledApp)
    hints = QGuiApplication.styleHints()
    assert hints is not None
    hints.colorSchemeChanged.emit(QtNamespace.ColorScheme.Dark)

    session.shutdown()

    assert window_colour(qapp) == before


@needs_qlementine
def test_shutdown_restores_the_style_font_and_palette(
    qapp: QApplication, build: BuildSession
) -> None:
    """Put back the application's style, font and palette at shutdown."""
    font = QFont(qapp.font())
    font.setPointSize(font.pointSize() + 3)
    palette = QPalette(qapp.palette())
    palette.setColor(QPalette.ColorRole.Window, QColor("#102030"))
    earlier = (style_name(qapp), qapp.font(), qapp.palette())
    qapp.setFont(font)
    qapp.setPalette(palette)
    try:
        build(StyledApp).shutdown()
        restored = (style_name(qapp), qapp.font().toString(), window_colour(qapp))
    finally:
        qapp.setFont(earlier[1])
        qapp.setPalette(QPalette())

    assert restored == (earlier[0], font.toString(), QColor("#102030"))


def test_a_missing_package_skips_the_style_and_names_the_extra(
    qapp: QApplication,
    build: BuildSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Start the session unstyled when qlementine's package is missing, logging the extra that installs it."""
    monkeypatch.setitem(qlementine.MODULES, API, "no_such_qlementine_package")
    before = style_name(qapp)

    with caplog.at_level(logging.ERROR, logger="redsun"):
        session = build(StyledApp)

    assert session.hooks[QtHook.CONFIGURE_APPLICATION] == ()
    assert style_name(qapp) == before
    assert f"redsun[{qlementine.EXTRAS[API]}]" in caplog.text
    assert "No module named 'no_such_qlementine_package'" in caplog.text


@needs_qlementine
def test_a_theme_file_replaces_the_built_in_theme_of_its_scheme(
    qapp: QApplication, build: BuildSession, lab_theme: Path
) -> None:
    """Use the dark theme file under the dark scheme, and qlementine's light theme under the light one."""
    styled(build, dark=str(lab_theme))
    hints = QGuiApplication.styleHints()
    assert hints is not None

    hints.colorSchemeChanged.emit(QtNamespace.ColorScheme.Dark)
    dark = window_colour(qapp).name()
    hints.colorSchemeChanged.emit(QtNamespace.ColorScheme.Light)

    assert dark == LAB_WINDOW
    assert not is_dark(qapp)


@needs_qlementine
def test_animations_can_be_turned_off(qapp: QApplication, build: BuildSession) -> None:
    """Turn qlementine's animations off when the session file says so."""
    styled(build, animations=False)
    # the style is qlementine's own class, which the stubs here don't know
    style: Any = qapp.style()

    assert not style.animationsEnabled()


@needs_qlementine
def test_a_theme_file_that_cannot_be_read_skips_the_style_naming_it(
    qapp: QApplication,
    build: BuildSession,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Start unstyled when a theme file cannot be read, logging the file and its scheme."""
    missing = tmp_path / "missing.json"
    before = style_name(qapp)

    with caplog.at_level(logging.ERROR, logger="redsun"):
        session = styled(build, light=str(missing))

    assert session.hooks[QtHook.CONFIGURE_APPLICATION] == ()
    assert style_name(qapp) == before
    assert f"the light theme file {missing} does not exist" in caplog.text


@pytest.mark.parametrize(
    "kwargs",
    [{"dark": 3}, {"light": ["lab.json"]}, {"animations": "false"}],
    ids=["number", "list", "text"],
)
def test_a_keyword_of_the_wrong_type_is_refused(kwargs: dict[str, Any]) -> None:
    """Refuse a theme that is not a path and an animations value that is not true or false."""
    with pytest.raises(TypeError, match=f"{next(iter(kwargs))} must be"):
        QlementineStyle(**kwargs)
