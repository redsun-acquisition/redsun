"""The configuration of a set of devices, read, followed and written."""

from __future__ import annotations

from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING

from ophyd_async.core import Device, SignalR, walk_devices
from psygnal import Signal

from redsun.log import Loggable
from redsun.utils.devices import (
    Configuration,
    device_path,
    held_by,
    read_configuration,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from bluesky.protocols import Reading
    from ophyd_async.core import AsyncConfigurable


class DeviceConfiguration(Loggable):
    """The configuration of a set of devices: read, followed, and written.

    Each device is added under an owner, the name the session knows it by,
    and every key it holds belongs to that owner. A value changed on a device,
    or read back after a write, is reported on `sig_changed`.
    """

    sig_changed = Signal(str, object)
    """Key and value of a configuration signal, when it changes and after a write."""

    def __init__(self, name: str) -> None:
        """Hold no device yet; *name* names the owner in log records."""
        self.name = name
        self._configuration = Configuration(descriptors={}, readings={}, writable={})
        self._held: frozenset[str] = frozenset()
        self._unsubscribers: list[Callable[[], None]] = []

    @property
    def configuration(self) -> Configuration:
        """Everything added so far.

        An entry whose signal cannot be written has `:readonly` appended to
        its source.
        """
        return self._configuration

    async def add(
        self,
        owner: str,
        device: AsyncConfigurable,
        *,
        owner_device: Device | None = None,
    ) -> Configuration:
        """Read *device*'s configuration, follow its signals, and file it under *owner*.

        Returns the configuration of *device* alone. Nothing is kept when
        reading fails or the call is cancelled. A key, or the owner, whose
        device is not among its parent's children gets no path.

        Parameters
        ----------
        owner_device
            The device *owner* names, when it is not *device*.
        """
        configuration = await read_configuration(device)
        signals = walk_devices(device).values() if isinstance(device, Device) else ()
        for signal in signals:
            if isinstance(signal, SignalR) and signal.name in configuration.readings:
                self._unsubscribers.append(partial(signal.clear_sub, self._relay))
                signal.subscribe_reading(self._relay)
                with suppress(LookupError):
                    configuration.paths[signal.name] = device_path(signal)
        named = device if owner_device is None else owner_device
        if isinstance(named, Device):
            with suppress(LookupError):
                configuration.paths[owner] = device_path(named)
        self._configuration.descriptors.update(configuration.descriptors)
        self._configuration.readings.update(configuration.readings)
        self._configuration.writable.update(configuration.writable)
        self._configuration.owners.update(
            dict.fromkeys(configuration.descriptors, owner)
        )
        self._configuration.paths.update(configuration.paths)
        return configuration

    async def configure(self, key: str, value: object) -> str:
        """Write *value* to *key*, report what it reads back, and return its owner.

        A write to a signal that is held, or that sits below a held device, is
        not made, and the value is still read back and reported.

        Raises
        ------
        KeyError
            If *key* names no writable configuration signal.
        """
        signal = self._configuration.writable[key]
        owner = self._configuration.owners[key]
        if held_by(signal, self._held):
            self.logger.warning(f"Not setting {key}: a plan holds it")
        else:
            try:
                await signal.set(value)
            except Exception:
                self.logger.exception(f"Setting {key} to {value!r} failed")
        try:
            current = await signal.get_value()
        except Exception:
            self.logger.exception(f"Reading {key} back failed")
            return owner
        self.sig_changed.emit(key, current)
        return owner

    def set_locked(self, names: frozenset[str]) -> None:
        """Refuse writes to the signals in *names* and below the devices in it."""
        self._held = names

    def remove_all(self) -> None:
        """Stop following every signal added."""
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()

    def _relay(self, reading: dict[str, Reading[object]]) -> None:
        # a receiver that raises would reach whatever set the device's signal
        try:
            for key, entry in reading.items():
                self.sig_changed.emit(key, entry["value"])
        except Exception:
            self.logger.exception("Relaying a configuration value failed")
