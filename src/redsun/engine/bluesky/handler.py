"""Bluesky handler class."""

from typing import TYPE_CHECKING

from bluesky.run_engine import RunEngine
from sunflare.engine import EngineHandler, DetectorModel, MotorModel
from sunflare.errors import UnsupportedDeviceType

if TYPE_CHECKING:
    from typing import Any, Union

    from sunflare.config import RedSunInstanceInfo
    from sunflare.engine.bluesky import BlueskyDetectorModel, BlueskyMotorModel
    from sunflare.virtualbus import VirtualBus


class BlueskyHandler(EngineHandler):
    r"""
    ExEngine handler class.

    All models compatible with ExEngine are registered here at application startup.

    Parameters
    ----------
    config_options : RedSunInstanceInfo
        Configuration options for the RedSun instance.
    virtual_bus : VirtualBus
        The virtual bus instance for the RedSun instance.
    module_bus : VirtualBus
        The virtual bus instance for the module.
    """

    _detectors: "dict[str, BlueskyDetectorModel]" = {}
    _motors: "dict[str, BlueskyMotorModel]" = {}

    def __init__(
        self,
        config_options: "RedSunInstanceInfo",
        virtual_bus: "VirtualBus",
        module_bus: "VirtualBus",
    ) -> None:
        super().__init__(config_options, virtual_bus, module_bus)
        self._engine = RunEngine()  # type: ignore[no-untyped-call]

    def register_device(  # noqa: D102
        self, name: str, device: "Union[BlueskyDetectorModel, BlueskyMotorModel]"
    ) -> None:
        if isinstance(device, DetectorModel):
            self._detectors[name] = device
        elif isinstance(device, MotorModel):
            self._motors[name] = device
        else:
            raise ValueError(
                f"Device of type {type(device)} not supported by ExEngine."
            )

    @property
    def detectors(self) -> "dict[str, BlueskyDetectorModel]":
        """Dictionary containing all the registered ExEngine detectors."""
        return self._detectors

    @property
    def motors(self) -> "dict[str, BlueskyMotorModel]":
        """Dictionary containing all the registered ExEngine motors."""
        return self._motors

    @property
    def engine(self) -> RunEngine:
        """Execution engine instance."""
        return self._engine

    @property
    def lights(self) -> "dict[str, Any]":
        """Dictionary containing all the registered ExEngine light sources."""
        raise UnsupportedDeviceType("Bluesky", "Light")

    @property
    def scanners(self) -> "dict[str, Any]":
        """Dictionary containing all the registered ExEngine scanners."""
        raise UnsupportedDeviceType("Bluesky", "Scanner")
