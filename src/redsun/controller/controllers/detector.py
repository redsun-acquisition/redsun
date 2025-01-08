"""Bluesky detector controller module."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any, Optional, cast

from bluesky.plans import count
from numpy.typing import NDArray
from sunflare.controller import ControllerProtocol
from sunflare.log import Loggable
from sunflare.virtual import Signal, VirtualBus

from redsun.controller.protocols import DetectorModel

if TYPE_CHECKING:
    from bluesky.utils import MsgGenerator
    from sunflare.config import ControllerInfo
    from sunflare.engine.handler import EventName

    from redsun.engine.bluesky import BlueskyHandler
    from redsun.virtual import HardwareVirtualBus


class DetectorController(ControllerProtocol, Loggable):
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
    sigImage : Signal(dict[str, NDArray[Any])
        Signal emitted when new data is available from a detector.
    """

    _handler: BlueskyHandler
    _virtual_bus: HardwareVirtualBus

    sigImage: Signal = Signal(dict[str, NDArray[Any]])

    def __init__(
        self,
        ctrl_info: ControllerInfo,
        handler: BlueskyHandler,
        virtual_bus: HardwareVirtualBus,
        module_bus: VirtualBus,
    ) -> None:
        self._ctrl_info = ctrl_info
        self._handler = handler
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus

        self._detectors: dict[str, DetectorModel] = {
            name: detector
            for name, detector in self._handler.models.items()
            if isinstance(detector, DetectorModel)
        }

        def snap_plan(detectors: list[DetectorModel]) -> MsgGenerator[Any]:
            """Take a snapshot from a series of detectors.

            Parameters
            ----------
            detectors : list[DetectorModel]
                List of detectors to take snapshots from
            """
            yield from count(detectors, num=1)

        def live_plan(detectors: list[DetectorModel]) -> MsgGenerator[Any]:
            """Launch a series of detectors for live acquisition.

            The frame rate is kept fixed at 30 fps; for detectors with slower acquisition rates,
            the latest frame is kept visualized until a new one is available.

            Parameters
            ----------
            detectors : list[DetectorModel]
                List of detectors to launch for live acquisition
            """
            yield from count(detectors, num=None, delay=0.033)

        self._snap_plan = snap_plan
        self._live_plan = live_plan

        self._handler.register_plan(
            self.__clsname__,
            "Snap",
            partial(self._snap_plan, list(self._detectors.values())),
        )
        self._handler.register_plan(
            self.__clsname__,
            "Live",
            partial(self._live_plan, list(self._detectors.values())),
        )

        self._event_token: Optional[int] = None

    def shutdown(self) -> None:  # noqa: D102
        for detector in self._detectors.values():
            if hasattr(detector, "shutdown"):
                detector.shutdown()

    def registration_phase(self) -> None:  # noqa: D102
        ...

    def connection_phase(self) -> None:  # noqa: D102
        ...

    def snap(self, detectors: list[str]) -> None:
        """Take a snapshot from a series of detectors.

        The method subscribes to the event stream, launches
        the Snap plan and then unsubscribes from the event stream.

        Parameters
        ----------
        detectors : Sequence[str]
            Sequence of detector names to take snapshots from.
        """
        dets = [self._detectors[name] for name in detectors]
        self._handler.register_plan(
            self.__clsname__, "Snap", partial(self._snap_plan, dets)
        )
        token = self._handler.subscribe(self.read_event, name="event")
        self._handler.execute(self.__clsname__, "Snap")
        self._handler.unsubscribe(token)

    def live(self, detectors: list[str], toggled: bool) -> None:
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
        dets = [self._detectors[name] for name in detectors]
        if toggled:
            self._handler.register_plan(
                self.__clsname__, "Live", partial(self._live_plan, dets)
            )
            self._event_token = self._handler.subscribe(self.read_event, name="event")
            self._handler.execute(self.__clsname__, "Live")
        else:
            self._handler.halt()
            self._handler.unsubscribe(cast(int, self._event_token))
            self._event_token = None

    def read_event(self, _: EventName, document: dict[str, Any]) -> None:
        """Handle an "event" document.

        This is a callback method called when an "event" document is received
        from the event stream.

        Parameters
        ----------
        name : EventName
            The name of the document type; should always be "event". Unused.
        document : dict[str, Any]
            The received "event" document.

        Notes
        -----
        Emits the `sigImage` signal with the data from the document.
        The data is expected to be a dictionary with the keys being the detector names
        and the values being the data arrays.
        """
        self.sigImage.emit(document["data"])
