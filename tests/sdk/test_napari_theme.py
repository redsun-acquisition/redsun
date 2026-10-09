"""Tests for napari's stylesheet template and icons, as `redsun` fills them."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from redsun.qt.styles._vendor._napari.icons import write_icons
from redsun.qt.styles._vendor._napari.theme import (
    DARK,
    LIGHT,
    Theme,
    darken,
    lighten,
    opacity,
    stylesheet,
    template,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

TEMPLATE = (
    "QWidget { background: {{ background }}; color: {{ text }}; "
    "border: 1px solid {{ darken(foreground, 20) }}; "
    "font-size: {{ increase(font_size, 1) }}; } "
    'QLabel { color: {{ opacity(text, 90) }}; image: url("theme_{{ id }}:/check.svg"); }'
)


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (lambda: darken("rgb(46, 51, 62)", 20, "dark"), "rgb(36, 40, 50)"),
        (lambda: lighten("rgb(46, 51, 62)", 20, "dark"), "rgb(86, 93, 107)"),
        (lambda: darken("rgb(221, 218, 216)", 20, "light"), "rgb(228, 225, 223)"),
        (lambda: opacity("rgb(240, 241, 242)", 90), "rgba(240, 241, 242, 90)"),
    ],
    ids=["darken-dark", "lighten-dark", "darken-light", "opacity"],
)
def test_the_colour_functions_give_napari_values(
    call: Callable[[], str], expected: str
) -> None:
    """Shift and fade colours exactly as napari 0.9.2 does."""
    assert call() == expected


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS scales size steps by 96/72")
def test_a_template_fills_as_napari_fills_it() -> None:
    """Fill keys, colour functions, sizes and image URLs as napari 0.9.2 does."""
    filled = template(TEMPLATE, DARK)

    assert filled == (
        "QWidget { background: rgb(35, 36, 43); color: rgb(240, 241, 242); "
        "border: 1px solid rgb(36, 40, 50); font-size: 10.0pt; } "
        'QLabel { color: rgba(240, 241, 242, 90); image: url("theme_dark:/check.svg"); }'
    )


@pytest.mark.parametrize("theme", [DARK, LIGHT], ids=["dark", "light"])
def test_the_whole_stylesheet_fills_with_no_placeholder_left(
    theme: Theme, tmp_path: Path
) -> None:
    """Leave no placeholder in napari's three stylesheets once a theme fills them."""
    assert "{{" not in stylesheet(theme, tmp_path)


def test_the_icons_are_written_in_the_theme_colours(tmp_path: Path) -> None:
    """Write each icon at full and half opacity, coloured from the theme."""
    folder = write_icons(DARK, tmp_path)

    check = (folder / "check.svg").read_text(encoding="utf-8")
    assert "fill: #d1d2d4; opacity: 1;" in check
    assert (folder / "check_50.svg").exists()
    assert "fill: #e3b617" in (folder / "warning.svg").read_text(encoding="utf-8")
    assert len(list(folder.glob("*.svg"))) == 2 * 79
