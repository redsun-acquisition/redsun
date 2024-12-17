"""Bluesky detector controller module."""

from __future__ import annotations

import threading

from concurrent.futures import ThreadPoolExecutor, Future
from typing import TYPE_CHECKING

from sunflare.virtualbus import Signal, VirtualBus
from sunflare.controller.bluesky import BlueskyController
from sunflare.config import ControllerInfo
from sunflare.engine.bluesky.registry import BlueskyDeviceRegistry
from sunflare.log import Loggable
from sunflare.types import Buffer

from redsun.virtual import HardwareVirtualBus

if TYPE_CHECKING:
    from typing import Sequence, Any, Tuple

    import numpy.typing as npt


class DetectorController(BlueskyController, Loggable):
    """Detector controller protocol."""

    _virtual_bus: HardwareVirtualBus

    sigImage: Signal = Signal(dict[str, Tuple[npt.NDArray[Any], dict[str, Any]]])

    def __init__(
        self,
        ctrl_info: ControllerInfo,
        registry: BlueskyDeviceRegistry,
        virtual_bus: HardwareVirtualBus,
        module_bus: VirtualBus,
    ) -> None:
        super().__init__(ctrl_info, registry, virtual_bus, module_bus)
        self._buffer: dict[str, Tuple[npt.NDArray[Any], dict[str, Any]]] = {}
        self._live = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=len(registry.detectors))
        self._futures: list[Future[None]] = []

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
        try:
            for det in detectors:
                status = self._registry.detectors[det].stage()
                if not status.done:
                    raise RuntimeError(f"Failed to stage detector {det}")
                data = self._registry.detectors[det].read()
                status = self._registry.detectors[det].unstage()
                if not status.done:
                    raise RuntimeError(f"Failed to unstage detector {det}")
                # TODO: adjust the return type of read() to match the type hint
                self._buffer[det] = data  # type: ignore
            self.sigImage.emit(self._buffer)
        except RuntimeError as e:
            self.error(str(e))

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
        if toggled:
            self._live.set()
            for det in detectors:
                self._futures.append(
                    self._executor.submit(self._background_collector, det)
                )
        else:
            self._live.clear()
            for future in self._futures:
                # wait for all threads to finish
                future.result()
            self._futures.clear()

    def _background_collector(self, detector: str) -> None:
        """Collect data in the background.

        A ThreadPoolExecutor is used to collect data from multiple detectors. A thread
        is launched for each detector, which collects data and emits a signal when
        new data is available.

        Parameters
        ----------
        detector : str
            Detector name to collect data from.
        """
        det = self._registry.detectors[detector]
        buf: Buffer = {}
        det.stage()
        while self._live.is_set():
            # TODO: adjust the return type of read() to match the type hint
            buf[detector] = det.read()  # type: ignore
            self.sigImage.emit(buf)
        det.unstage()
