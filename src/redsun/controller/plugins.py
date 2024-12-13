"""Redsun plugin manager module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sunflare.virtualbus import Signal

import sys

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

if TYPE_CHECKING:
    from typing import Type, Union, TypeAlias, Any, Literal, Sequence, Tuple

    from sunflare.virtualbus import ModuleVirtualBus
    from sunflare.config import (
        DetectorModelInfo,
        MotorModelInfo,
    )
    from sunflare.engine import DetectorModel, MotorModel

    from redsun.controller.virtualbus import HardwareVirtualBus

ModelInfoTypes: TypeAlias = Union[Type[DetectorModelInfo], Type[MotorModelInfo]]
ModelTypes: TypeAlias = Union[Type[DetectorModel], Type[MotorModel]]

Registry: TypeAlias = dict[
    Literal["motors", "detectors"], list[Tuple[str, ModelInfoTypes, ModelTypes]]
]


class PluginManager:
    """Plugin manager class.

    This manager uses `importlib.metadata` to discover and load Redsun-compatible plugins.

    Parameters
    ----------
    virtual_bus : HardwareVirtualBus
        Hardware virtual bus.
    module_bus : ModuleVirtualBus
        Module virtual bus.
    """

    sigNewDevices: Signal = Signal(str, Registry)

    def __init__(
        self,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
    ):
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus
        self._namespace = "redsun.plugins"

    def registration_phase(self) -> None:  # noqa: D102
        # nothing to do here
        ...

    def connection_phase(self) -> None:  # noqa: D102
        self.sigNewDevices.connect(self._virtual_bus.sigNewDevices)

    def load_plugins(
        self, config: dict[str, Any], groups: Sequence[Literal["motors", "detectors"]]
    ) -> Registry:  # noqa: D102
        """Load plugins from the given configuration.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration dictionary.
        groups : Sequence[Literal["motors", "detectors"]]
            List of groups to load plugins from.

        Returns
        -------
        Registry
            A dictionary containing the loaded plugins classes.
        """
        registry: Registry = {group: [] for group in groups}
        for group in groups:
            input: dict[str, Any] = config[group]
            plugins = entry_points(group=".".join([self._namespace, group]))
            config_plugins = [ep for ep in plugins if "_config" in ep.name]
            model_plugins = [ep for ep in plugins if "_config" not in ep.name]
            for cfg_ep, model_ep in zip(config_plugins, model_plugins):
                # Retrieve the name of the config builder
                cfg_cls = cfg_ep.value.split(":")[1]
                # Retrieve the name of the actual device model
                bld_cls = cfg_cls[:-4]
                cfg_builder = cfg_ep.load()
                if not all(
                    [
                        issubclass(cfg_builder, cfg_type)
                        for cfg_type in [DetectorModelInfo, MotorModelInfo]
                    ]
                ):
                    raise TypeError(
                        f"Loaded model info {cfg_builder} is not a subclass of any recognized model info class"
                    )
                for device_name, values in input.items():
                    if values["model_name"] == bld_cls:
                        builder = model_ep.load()
                        registry[group].append((device_name, cfg_builder, builder))
                        break
                # pop the found device from the input to speed up the search
                input.pop(device_name)
        return registry
