"""Qt image viewer widget module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ndv import NDViewer
from qtpy.QtWidgets import QVBoxLayout
from sunflare.view.qt import BaseWidget
from sunflare.virtualbus import VirtualBus, slot

if TYPE_CHECKING:
    from redsun.virtual import HardwareVirtualBus


class ImageViewWidget(BaseWidget):
    """Image viewer widget.

    Wraps the NDViewer widget to display images.

    Parameters
    ----------
    virtual_bus : HardwareVirtualBus
        The virtual bus instance for the RedSun instance.
    module_bus : VirtualBus
        The inter-module virtual bus instance.
    """

    _virtual_bus: HardwareVirtualBus

    def __init__(self, virtual_bus: HardwareVirtualBus, module_bus: VirtualBus) -> None:
        super().__init__(virtual_bus, module_bus)
        layout = QVBoxLayout()
        self._viewer = NDViewer(None)
        layout.addWidget(self._viewer)
        self.setLayout(layout)

    def registration_phase(self) -> None:  # noqa: D102
        # inherited docstring
        # nothing to do
        ...

    def connection_phase(self) -> None:  # noqa: D102
        self._virtual_bus.sigNewImage.connect(self.update_image)

    @slot
    def update_image(self, image: Any) -> None:
        """Update the image displayed in the viewer.

        Parameters
        ----------
        image : Any
            Dictionary containing all registered detectors and their data/metadata.
        """
        self._viewer.set_data(image)
