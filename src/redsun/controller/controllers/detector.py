r"""Detector controller module. It provides a basic protocol to interface with detector devices.

Detector controllers are the direct link between the respective models and the user interface. \
Signals emitted from the UI are captured by the controller, and are appropriately \
translated into commands that the detector can execute. Usually when a workflow is running, \
this connection is disabled to prevent accidental user input from interfering with the workflow execution.

The exception to this rule is that when a detector captures new data, this is always sent to the viewer.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from typing import Sequence

    from sunflare.virtual import Signal


class DetectorControllerProtocol(Protocol):
    """Detector controller protocol."""

    sigNewImage: Signal

    @abstractmethod
    def snap(self, detectors: Sequence[str]) -> None:
        """Take a snapshot from a series of detectors."""
        ...

    @abstractmethod
    def live(self, detectors: Sequence[str], toggle: bool) -> None:
        """Launch a series of detectors for live acquisition.

        The frame rate is kept fixed at 30 fps; for detectors with slower acquisition rates,
        the latest frame is kept visualized until a new one is available.

        Parameters
        ----------
        detectors : Sequence[str]
            List of detector names to launch for live acquisition.
        toggle : bool
            If `True`, start live acquisition; if `False`, stop it.
        """
        ...
