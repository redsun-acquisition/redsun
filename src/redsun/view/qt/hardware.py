# noqa: D100
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redsun.view.qt.widgets import ImageViewWidget
    from sunflare.view.qt import BaseWidget


# TODO: maybe do a dataclass...?
class RedSunHardwareWidgetContainer:  # noqa: D101
    """RedSun hardware widget container class.

    This is not a real widget class, but only a container for the widget references.
    These are then instantiated in the main view window according to a specific layout.
    """

    # image widget: center of the main window
    _image_viewer: ImageViewWidget

    # device widgets: left side of the main window
    _device_widgets: dict[str, BaseWidget] = {}

    # controller widgets: right side of the main window
    _controller_widgets: dict[str, BaseWidget] = {}

    @property
    def image_viewer(self) -> ImageViewWidget:
        """Image viewer widget."""
        return self._image_viewer

    @image_viewer.setter
    def image_viewer(self, widget: ImageViewWidget) -> None:
        self._image_viewer = widget

    @property
    def device_widgets(self) -> dict[str, BaseWidget]:
        """Device widgets."""
        return self._device_widgets

    @property
    def controller_widgets(self) -> dict[str, BaseWidget]:
        """Controller widgets."""
        return self._controller_widgets
