"""Qt image viewer widget module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ndv import NDViewer
from qtpy.QtWidgets import QVBoxLayout
from sunflare.view.qt import BaseQtWidget
from sunflare.virtual import slot

if TYPE_CHECKING:
    from numpy.typing import NDArray
    from sunflare.config import RedSunSessionInfo
    from sunflare.virtual import ModuleVirtualBus

    from redsun.virtual import HardwareVirtualBus


class ImageViewWidget(BaseQtWidget):
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

    def __init__(
        self,
        config: RedSunSessionInfo,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
    ) -> None:
        super().__init__(config, virtual_bus, module_bus)
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
    def update_image(self, image: dict[str, NDArray[Any]]) -> None:
        """Update the image displayed in the viewer.

        Parameters
        ----------
        image : dict[str, NDArray[Any]]
            Dictionary with the detector names as keys and the read images as values.
        """
        self._viewer.set_data(image)
