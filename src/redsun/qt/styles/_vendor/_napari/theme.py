"""napari's two built-in themes and the template filling its stylesheets.

Derived from napari's `napari/utils/theme.py`, under napari's BSD-3 licence
in `LICENSE` beside this module.
"""

from __future__ import annotations

import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

STYLES = Path(__file__).parent / "styles"
FONT_SIZE = "12pt" if sys.platform == "darwin" else "9pt"
INCREASE = re.compile(r"{{\s?increase\((\w+),?\s?([-\d]+)?\)\s?}}")
DECREASE = re.compile(r"{{\s?decrease\((\w+),?\s?([-\d]+)?\)\s?}}")
GRADIENT = re.compile(r"([vh])gradient\((.+)\)")
DARKEN = re.compile(r"{{\s?darken\((\w+),?\s?([-\d]+)?\)\s?}}")
LIGHTEN = re.compile(r"{{\s?lighten\((\w+),?\s?([-\d]+)?\)\s?}}")
OPACITY = re.compile(r"{{\s?opacity\((\w+),?\s?([-\d]+)?\)\s?}}")
RGB = re.compile(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)")


@dataclass(frozen=True)
class Theme:
    """One of napari's colour themes, every colour written `rgb(r, g, b)`."""

    name: str
    """`dark` or `light`; also names the folder the stylesheet's images come from."""
    background: str
    """The window's background."""
    foreground: str
    """Panels and controls on the background."""
    primary: str
    """Controls such as buttons and fields."""
    secondary: str
    """Controls drawn over the primary colour."""
    highlight: str
    """A control under the pointer."""
    text: str
    """Text."""
    icon: str
    """The icons' colour."""
    warning: str
    """Warnings."""
    error: str
    """Errors."""
    current: str
    """The selected or checked item."""
    console: str
    """The console's background."""
    canvas: str
    """The canvas's background."""
    font_size: str = FONT_SIZE
    """The base font size, in points."""


DARK: Final = Theme(
    name="dark",
    background="rgb(35, 36, 43)",
    foreground="rgb(46, 51, 62)",
    primary="rgb(66, 74, 84)",
    secondary="rgb(86, 95, 108)",
    highlight="rgb(97, 105, 110)",
    text="rgb(240, 241, 242)",
    icon="rgb(209, 210, 212)",
    warning="rgb(227, 182, 23)",
    error="rgb(153, 18, 31)",
    current="rgb(69, 96, 196)",
    console="rgb(18, 18, 18)",
    canvas="rgb(0, 0, 0)",
)

LIGHT: Final = Theme(
    name="light",
    background="rgb(235, 231, 230)",
    foreground="rgb(221, 218, 216)",
    primary="rgb(197, 195, 193)",
    secondary="rgb(180, 178, 175)",
    highlight="rgb(175, 172, 170)",
    text="rgb(30, 30, 33)",
    icon="rgb(62, 63, 65)",
    warning="rgb(227, 182, 23)",
    error="rgb(255, 18, 31)",
    current="rgb(160, 184, 255)",
    console="rgb(255, 255, 255)",
    canvas="rgb(255, 255, 255)",
)


def parse_rgb(colour: str) -> tuple[int, int, int]:
    """Return the red, green and blue of a colour written `rgb(r, g, b)`.

    Raises
    ------
    ValueError
        If *colour* is written any other way.
    """
    match = RGB.fullmatch(colour)
    if match is None:
        raise ValueError(f"expected a colour written rgb(r, g, b), got {colour!r}")
    red, green, blue = (int(value) for value in match.groups())
    return red, green, blue


def shift_luminance(
    rgb: tuple[int, int, int], percentage: float
) -> tuple[int, int, int]:
    """Darken or lighten a colour, keeping its hue and how saturated it looks."""
    r, g, b = (float(value) for value in rgb)
    percentage /= 100
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    if percentage >= 0:
        target = luminance + (255.0 - luminance) * percentage
    else:
        target = luminance * (1.0 + percentage)
    target = max(0.0, min(255.0, target))
    if luminance < 1.0:
        grey = max(0, min(255, int(target)))
        return grey, grey, grey
    scale = target / luminance
    r, g, b = r * scale, g * scale, b * scale
    # napari's coefficients: light colours look more saturated than dark ones
    saturation = (
        1.0 / (1.0 + (scale - 1.0) * 0.5) if scale > 1.0 else 1.0 + (1.0 - scale) * 0.5
    )
    grey_level = (r + g + b) / 3.0
    r, g, b = (grey_level + (value - grey_level) * saturation for value in (r, g, b))
    return max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b)))


def darken(colour: str, percentage: float, theme_type: str) -> str:
    """Return *colour* shifted by *percentage*: darker in a dark theme, lighter in a light one."""
    shift = percentage * (-1 if theme_type == "dark" else 1)
    r, g, b = shift_luminance(parse_rgb(colour), shift)
    return f"rgb({r}, {g}, {b})"


def lighten(colour: str, percentage: float, theme_type: str) -> str:
    """Return *colour* shifted by *percentage*: lighter in a dark theme, darker in a light one."""
    shift = percentage * (-1 if theme_type == "light" else 1)
    r, g, b = shift_luminance(parse_rgb(colour), shift)
    return f"rgb({r}, {g}, {b})"


def opacity(colour: str, value: int) -> str:
    """Return *colour* with an alpha of *value*, clamped to 0..255."""
    r, g, b = parse_rgb(colour)
    return f"rgba({r}, {g}, {b}, {max(min(int(value), 255), 0)})"


def size_step(pt: str) -> float:
    """Return a font size step in points, scaled by 96/72 on macOS."""
    return float(pt) * 96 / 72 if sys.platform == "darwin" else float(pt)


def increase(font_size: str, pt: str) -> str:
    """Return *font_size* (such as `9pt`) made larger by *pt* points."""
    return f"{int(font_size[:-2]) + size_step(pt)}pt"


def decrease(font_size: str, pt: str) -> str:
    """Return *font_size* (such as `9pt`) made smaller by *pt* points."""
    return f"{int(font_size[:-2]) - size_step(pt)}pt"


def gradient(stops: Sequence[str], horizontal: bool) -> str:
    """Return a Qt linear gradient through *stops*, evenly numbered from 0."""
    end = "x2: 1, y2: 0" if horizontal else "x2: 0, y2: 1"
    numbered = ", ".join(f"stop: {n} {stop}" for n, stop in enumerate(stops))
    return f"qlineargradient(x1: 0, y1: 0, {end}, {numbered})"


def template(css: str, theme: Theme) -> str:
    """Return *css* with its placeholders filled from *theme*.

    napari's `id` and `type` placeholders both read the theme's `name`.
    """
    values = {**asdict(theme), "id": theme.name, "type": theme.name}
    css = INCREASE.sub(lambda m: increase(values[m[1]], m[2]), css)
    css = DECREASE.sub(lambda m: decrease(values[m[1]], m[2]), css)
    css = GRADIENT.sub(
        lambda m: gradient([stop.strip() for stop in m[2].split("-")], m[1] == "h"), css
    )
    css = DARKEN.sub(lambda m: darken(values[m[1]], float(m[2]), theme.name), css)
    css = LIGHTEN.sub(lambda m: lighten(values[m[1]], float(m[2]), theme.name), css)
    css = OPACITY.sub(lambda m: opacity(values[m[1]], int(m[2])), css)
    for key, value in values.items():
        css = css.replace(f"{{{{ {key} }}}}", value)
    return css


def stylesheet(theme: Theme) -> str:
    """Return napari's three stylesheets, in order, filled from *theme*."""
    return "".join(
        template(path.read_text(encoding="utf-8"), theme)
        for path in sorted(STYLES.glob("*.qss"))
    )
