"""napari's icons, written in a theme's colours for its stylesheet to load.

Derived from napari's `napari/resources/_icons.py`, under napari's BSD-3
licence in `LICENSE` beside this module.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .theme import parse_rgb

if TYPE_CHECKING:
    from .theme import Theme

ICONS = Path(__file__).parent / "icons"
SVG_TAG = re.compile(r"(<svg[^>]*>)")
STYLE = """<style type="text/css">
path {{fill: {0}; opacity: {1};}}
polygon {{fill: {0}; opacity: {1};}}
circle {{fill: {0}; opacity: {1};}}
rect {{fill: {0}; opacity: {1};}}
</style>"""
COLOUR_KEYS = {"warning": "warning", "error": "error", "logo_silhouette": "foreground"}
"""Icons drawn in another of the theme's colours than `icon`."""


def write_icons(theme: Theme, folder: Path) -> Path:
    """Write every icon in *theme*'s colours into *folder*, and return *folder*.

    Each icon is written twice: `name.svg` opaque and `name_50.svg` at half
    opacity. A file already holding the same content is left as it is.
    """
    folder.mkdir(parents=True, exist_ok=True)
    for path in sorted(ICONS.glob("*.svg")):
        xml = path.read_text(encoding="utf-8")
        red, green, blue = parse_rgb(getattr(theme, COLOUR_KEYS.get(path.stem, "icon")))
        colour = f"#{red:02x}{green:02x}{blue:02x}"
        for suffix, opacity in (("", 1), ("_50", 0.5)):
            content = SVG_TAG.sub(rf"\g<1>{STYLE.format(colour, opacity)}", xml)
            target = folder / f"{path.stem}{suffix}.svg"
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                target.write_text(content, encoding="utf-8")
    return folder
