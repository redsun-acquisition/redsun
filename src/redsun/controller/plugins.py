"""Redsun plugin manager module."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from sunflare.virtualbus import Signal

import sys

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

if TYPE_CHECKING:
    from typing import Type, Union, TypeAlias

    from sunflare.virtualbus import ModuleVirtualBus
    from sunflare.config import (
        RedSunInstanceInfo,
        DetectorModelInfo,
        MotorModelInfo,
    )
    from sunflare.engine import DetectorModel, MotorModel

    from redsun.controller.virtualbus import HardwareVirtualBus

C = TypeVar("C", bound=Union[DetectorModelInfo, MotorModelInfo])
M = TypeVar("M", bound=Union[DetectorModel, MotorModel])

Registry: TypeAlias = dict[str, Union[DetectorModel, MotorModel]]


class PluginManager:
    """Plugin manager class.

    This manager uses `importlib.metadata` to discover and load Redsun-compatible plugins.

    Parameters
    ----------
    config : RedSunInstanceInfo
        RedSun instance configuration.
    virtual_bus : HardwareVirtualBus
        Hardware virtual bus.
    module_bus : ModuleVirtualBus
        Module virtual bus.
    """

    sigNewDevices: Signal = Signal(str, Registry)

    def __init__(
        self,
        config: RedSunInstanceInfo,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
    ):
        self._config = config
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus
        self._namespace = "redsun.plugins"

    def registration_phase(self) -> None:  # noqa: D102
        # nothing to do here
        ...

    def connection_phase(self) -> None:  # noqa: D102
        self.sigNewDevices.connect(self._virtual_bus.sigNewDevices)

    def build_models(
        self,
        group: str,
        config_class: Type[C],
        input: dict[str, dict[str, str]],
        *,
        _: Type[M],  # this is to avoid a mypy error
    ) -> None:
        """Build models from the given configuration.

        Redsun provides entry points for plugins of the following groups:

        - motors;
        - detectors;

        Each model expects two classes: one for configuration and one for the actual device model.
        The manager will inspect the given input configuration and:

        - build the configuration class;
        - build the device model class;
        - emit a signal with the built models.

        The DeviceRegistry will store the built models for access to the other controllers.

        Parameters
        ----------
        group : str
            Entry point group name (e.g. 'motors').
        config_class : Type[C]
            Configuration class type.
        input : dict[str, dict[str, str]]
            Input configuration dictionary.
        """
        registry: dict[str, M] = {}
        plugins = entry_points(group=".".join([self._namespace, group]))
        config_plugins = [ep for ep in plugins if "_config" in ep.name]
        model_plugins = [ep for ep in plugins if "_config" not in ep.name]
        for cfg_ep, model_ep in zip(config_plugins, model_plugins):
            cfg_cls = cfg_ep.value.split(":")[
                1
            ]  # Retrieve the name of the config builder
            bld_cls = cfg_cls[:-4]  # Retrieve the name of the actual device model
            cfg_builder: Type[C] = cfg_ep.load()
            if not issubclass(cfg_builder, config_class):
                raise TypeError(
                    f"Loaded config builder {cfg_builder} is not a subclass of {config_class}"
                )
            for device_name, values in input.items():
                if values["model_name"] == bld_cls:
                    cfg = cfg_builder(**values)  # type: ignore[arg-type]
                    registry[device_name] = model_ep.load()(device_name, cfg)
                    break
            input.pop(
                device_name
            )  # Pop the found device from the input to speed up the search

        # The built models are stored in the currently
        # active device registry.
        self.sigNewDevices.emit(group, registry)
