"""A presenter switching and dimming light sources."""

from __future__ import annotations

import asyncio
import math
from dataclasses import KW_ONLY, dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ophyd_async.core import AsyncConfigurable
from psygnal import Signal

from redsun.aio import run_coro
from redsun.injection import DevicesOf  # noqa: TC001
from redsun.log import Loggable
from redsun.ports import slot
from redsun.utils.devices import (
    Light,
    LightInfo,
    describe_light,
    dimmable,
    is_light,
)

from ._device_configuration import DeviceConfiguration

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from bluesky.protocols import Reading

    from redsun.utils.devices import Configuration


@runtime_checkable
class DescribesLights(Protocol):
    """A component describing the lights it switches."""

    @property
    def lights(self) -> Mapping[str, LightInfo]:
        """Each light's state and intensity range, by device name."""
        ...

    @property
    def configuration(self) -> Configuration:
        """The configuration of every light."""
        ...


@dataclass(eq=False)
class LightPresenter(Loggable):
    """Switch light sources on and off, and set their intensity.

    Every light is described and followed from the start; one that cannot be,
    within `timeout`, is left out with a warning. Writes to a light a plan
    holds are refused. While an intensity is being written, only the newest
    one asked for meanwhile is written after it.
    """

    sig_enabled = Signal(str, bool)
    """Device, and whether it is on, whenever it reads back."""

    sig_intensity = Signal(str, float)
    """Device and intensity, whenever it reads back."""

    sig_failed = Signal(str, str)
    """Device, and why a write was refused or failed."""

    sig_configuration = Signal(str, object)
    """Key and value of a configuration signal, when it changes and after a write."""

    name: str
    """Name of the presenter in its session."""

    _: KW_ONLY

    devices: DevicesOf[Light] = field(repr=False)
    """Devices of the session with an `enabled` signal."""

    include: list[str] | None = None
    """Names of the lights to keep; `None` keeps every light."""

    timeout: float = 10.0
    """Seconds a light may take to be described, followed, or written."""

    def __post_init__(self) -> None:
        for name in self.include or ():
            if name not in self.devices:
                self.logger.warning(
                    f"No device named {name} has an `enabled` signal to include"
                )
            elif not is_light(self.devices[name]):
                self.logger.warning(
                    f"{name} is left out: its `enabled` is not a boolean signal "
                    "it can write"
                )
        self._lights = {
            name: device
            for name, device in self.devices.items()
            if (self.include is None or name in self.include) and is_light(device)
        }
        self._configuration = DeviceConfiguration(self.name)
        self._configuration.sig_changed.connect(self.sig_configuration.emit)
        self._unsubscribers: list[Callable[[], None]] = []
        self._held: frozenset[str] = frozenset()
        self._wanted: dict[str, float] = {}
        self._writing: set[str] = set()
        try:
            self._info = run_coro(self._follow())
        except BaseException:
            self._unfollow()
            raise

    @property
    def lights(self) -> dict[str, LightInfo]:
        """Each light's state and intensity range, by device name."""
        return self._info

    @property
    def configuration(self) -> Configuration:
        """The configuration of every light.

        An entry whose signal cannot be written has `:readonly` appended to
        its source.
        """
        return self._configuration.configuration

    @slot(signal="sig_enabled")
    async def set_enabled(self, device: str, on: bool) -> None:
        """Switch *device* on or off.

        Raises
        ------
        KeyError
            If the presenter does not hold *device*.
        """
        light = self._lights[device]
        if device in self._held:
            self._refuse(device, "a plan holds it")
            return
        try:
            await asyncio.wait_for(light.enabled.set(on), self.timeout)
        except Exception as error:
            self.logger.exception(f"Switching {device} failed")
            self.sig_failed.emit(device, str(error) or type(error).__name__)

    @slot(signal="sig_intensity")
    async def set_intensity(self, device: str, value: float) -> None:
        """Set the intensity of *device*, in its units.

        Raises
        ------
        KeyError
            If the presenter does not hold *device*.
        """
        light = self._lights[device]
        if device in self._held:
            self._refuse(device, "a plan holds it")
            return
        if not dimmable(light):
            self._refuse(device, "it has no intensity")
            return
        info = self._info[device].intensity
        low, high = (None, None) if info is None else info.limits
        if (
            not math.isfinite(value)
            or (low is not None and value < low)
            or (high is not None and value > high)
        ):
            self._refuse(device, f"intensity {value:g} is outside {low} to {high}")
            return
        # an integer intensity takes whole numbers only
        self._wanted[device] = (
            round(value) if light.intensity.datatype is int else value
        )
        if device in self._writing:
            return
        self._writing.add(device)
        try:
            while (wanted := self._wanted.pop(device, None)) is not None:
                # a plan may have taken the light while this value waited
                if device in self._held:
                    self._refuse(device, "a plan holds it")
                    break
                try:
                    await asyncio.wait_for(light.intensity.set(wanted), self.timeout)
                except Exception as error:
                    self.logger.exception(f"Setting the intensity of {device} failed")
                    self.sig_failed.emit(device, str(error) or type(error).__name__)
        finally:
            self._writing.discard(device)

    @slot(signal="sig_configure")
    async def configure(self, key: str, value: object) -> None:
        """Write *value* to the configuration signal *key*, then report it.

        Raises
        ------
        KeyError
            If *key* names no writable configuration signal.
        """
        await self._configuration.configure(key, value)

    @slot
    def set_locked(self, names: frozenset[str]) -> None:
        """Hold the lights in *names* for a plan: no write reaches them."""
        self._held = names
        self._configuration.set_locked(names)

    def shutdown(self) -> None:
        """Stop following the lights."""
        self._unfollow()

    async def _follow(self) -> dict[str, LightInfo]:
        names = list(self._lights)
        followed = await asyncio.gather(*(self._follow_light(name) for name in names))
        info = {
            name: light_info
            for name, light_info in zip(names, followed, strict=True)
            if light_info is not None
        }
        self._lights = {name: self._lights[name] for name in info}
        return info

    async def _follow_light(self, name: str) -> LightInfo | None:
        light = self._lights[name]
        unsubscribers: list[Callable[[], None]] = []
        try:
            async with asyncio.timeout(self.timeout):
                info = await describe_light(light)
                relay = partial(self._relay, name, self.sig_enabled.emit, bool)
                unsubscribers.append(partial(light.enabled.clear_sub, relay))
                light.enabled.subscribe_reading(relay)
                if dimmable(light):
                    level = partial(self._relay, name, self.sig_intensity.emit, float)
                    unsubscribers.append(partial(light.intensity.clear_sub, level))
                    light.intensity.subscribe_reading(level)
                if isinstance(light, AsyncConfigurable):
                    await self._configuration.add(name, light)
        except BaseException as error:
            for unsubscribe in unsubscribers:
                unsubscribe()
            if not isinstance(error, Exception):
                raise
            self.logger.warning(f"Leaving out {name}: {error!r}")
            return None
        self._unsubscribers.extend(unsubscribers)
        return info

    def _unfollow(self) -> None:
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        self._configuration.remove_all()

    def _relay(
        self,
        device: str,
        emit: Callable[[str, object], None],
        kind: type,
        reading: dict[str, Reading[object]],
    ) -> None:
        # a receiver that raises would reach whatever set the light's signal
        try:
            emit(device, kind(next(iter(reading.values()))["value"]))
        except Exception:
            self.logger.exception(f"Relaying a readback of {device} failed")

    def _refuse(self, device: str, reason: str) -> None:
        self.logger.warning(f"Not writing {device}: {reason}")
        self.sig_failed.emit(device, reason)
