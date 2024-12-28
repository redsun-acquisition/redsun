"""Bluesky detector controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from sunflare.controller import BaseController
from sunflare.log import Loggable
from sunflare.virtual import Signal, VirtualBus

if TYPE_CHECKING:
    from collections import OrderedDict

    from bluesky.protocols import Reading
    from sunflare.config import ControllerInfo

    from redsun.engine.bluesky import BlueskyHandler
    from redsun.virtual import HardwareVirtualBus


class DetectorController(BaseController, Loggable):
    """Detector controller protocol.

    Parameters
    ----------
    ctrl_info : ControllerInfo
        Controller information.
    registry : DeviceRegistry
        Device registry.
    virtual_bus : HardwareVirtualBus
        Virtual bus.
    module_bus : VirtualBus
        Module bus.

    Attributes
    ----------
    sigImage : Signal
        Signal emitted when new data is available from a detector.
    """

    _handler: BlueskyHandler
    _virtual_bus: HardwareVirtualBus

    sigImage: Signal = Signal(object)

    def __init__(
        self,
        ctrl_info: ControllerInfo,
        handler: BlueskyHandler,
        virtual_bus: HardwareVirtualBus,
        module_bus: VirtualBus,
    ) -> None:
        super().__init__(ctrl_info, handler, virtual_bus, module_bus)
        self._buffer: dict[str, OrderedDict[str, Reading[Any]]] = {}

    def shutdown(self) -> None:  # noqa: D102
        for detector in self._handler.detectors:
            if hasattr(detector, "shutdown"):
                detector.shutdown()

    def registration_phase(self) -> None:  # noqa: D102
        ...

    def connection_phase(self) -> None:  # noqa: D102
        ...

    def snap(self, detectors: Sequence[str]) -> None:
        """Take a snapshot from a series of detectors.

        Parameters
        ----------
        detectors : Sequence[str]
            Sequence of detector names to take snapshots from.
        """
        # TODO: rewrite as a Bluesky plan
        ...

    def live(self, detectors: Sequence[str], toggled: bool) -> None:
        """Launch a series of detectors for live acquisition.

        The frame rate is kept fixed at 30 fps; for detectors with slower acquisition rates,
        the latest frame is kept visualized until a new one is available.

        Parameters
        ----------
        detectors : Sequence[str]
            Sequence of detector names to launch for live acquisition.
        toggle : bool
            If `True`, start live acquisition; if `False`, stop it.
        """
        # TODO: implement live acquisition via a Bluesky plan
        ...
