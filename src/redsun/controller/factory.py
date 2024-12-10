"""
The `factory` module contains all the tooling necessary for the dynamic loading of controllers and models.

RedSun operates by dynamically loading external plugins with different archetypes
(single or multiple controllers, single or multiple models, combination of controllers and models, etc.)
to create a unique running instance.

This module operates within the RedSun core code and is not exposed to the toolkit or the user.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from typing import Union, Type

    from redsun.controller.virtualbus import HardwareVirtualBus
    from redsun.engine.bluesky import BlueskyHandler
    from redsun.engine.exengine import ExEngineHandler

    from sunflare.virtualbus import ModuleVirtualBus
    from sunflare.config import (
        AcquisitionEngineTypes,
        RedSunInstanceInfo,
        ControllerInfo,
    )
    from sunflare.controller.bluesky import BlueskyController
    from sunflare.controller.exengine import ExEngineController
    from sunflare.engine.bluesky.registry import BlueskyDeviceRegistry
    from sunflare.engine.exengine.registry import ExEngineDeviceRegistry

RegistryFactoryType: TypeAlias = Union[
    Type[BlueskyDeviceRegistry], Type[ExEngineDeviceRegistry]
]
RegistryBuildType: TypeAlias = Union[BlueskyDeviceRegistry, ExEngineDeviceRegistry]

EngineFactoryType: TypeAlias = Union[Type[BlueskyHandler], Type[ExEngineHandler]]
EngineBuildType: TypeAlias = Union[BlueskyHandler, ExEngineHandler]

ControllerFactoryType: TypeAlias = Union[
    Type[BlueskyController], Type[ExEngineController]
]
ControllerBuildType: TypeAlias = Union[BlueskyController, ExEngineController]

__all__ = ["RegistryFactory", "EngineFactory", "ControllerFactory"]


class RegistryFactory:
    """Device registry factory."""

    def __init__(
        self,
        engine: AcquisitionEngineTypes,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
    ) -> None:
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus
        self.__registry_factory: RegistryFactoryType
        if engine == AcquisitionEngineTypes.BLUESKY:
            self.__registry_factory = BlueskyDeviceRegistry
        elif engine == AcquisitionEngineTypes.EXENGINE:
            self.__registry_factory = ExEngineDeviceRegistry
        else:
            raise ValueError(f"Invalid engine: {engine}")

    @property
    def factory(self) -> RegistryFactoryType:
        """Get the registry factory."""
        return self.__registry_factory

    def build(self, config: RedSunInstanceInfo) -> RegistryBuildType:
        """Build the registry."""
        return self.__registry_factory(config, self._virtual_bus, self._module_bus)


class EngineFactory:
    """Engine factory."""

    def __init__(
        self,
        engine: AcquisitionEngineTypes,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
    ) -> None:
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus
        self.__engine_factory: EngineFactoryType
        if engine == AcquisitionEngineTypes.BLUESKY:
            self.__engine_factory = BlueskyHandler
        elif engine == AcquisitionEngineTypes.EXENGINE:
            self.__engine_factory = ExEngineHandler
        else:
            raise ValueError(f"Invalid engine: {engine}")

    @property
    def factory(self) -> EngineFactoryType:
        """Get the registry factory."""
        return self.__engine_factory

    def build(self, config: RedSunInstanceInfo) -> EngineBuildType:
        """Build the registry."""
        return self.__engine_factory(config, self._virtual_bus, self._module_bus)


class ControllerFactory:
    """Controller factory.

    Parameters
    ----------
    virtual_bus : HardwareVirtualBus
        Hardware virtual bus.
    module_bus : ModuleVirtualBus
        Module virtual bus.
    """

    def __init__(
        self,
        engine: AcquisitionEngineTypes,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
    ) -> None:
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus
        self.__controller_factor: ControllerFactoryType
        if engine == AcquisitionEngineTypes.BLUESKY:
            self.__controller_factor = BlueskyController
        elif engine == AcquisitionEngineTypes.EXENGINE:
            self.__controller_factor = ExEngineController
        else:
            raise ValueError(f"Invalid engine: {engine}")

    @property
    def factory(self) -> ControllerFactoryType:
        """Get the controller factory."""
        return self.__controller_factor

    def build(
        self, info: ControllerInfo, registry: RegistryBuildType
    ) -> ControllerBuildType:
        """Build the controller."""
        controller = self.__controller_factor(
            info,
            registry,  # type: ignore
            self._virtual_bus,
            self._module_bus,
        )
        controller.registration_phase()
        return controller
