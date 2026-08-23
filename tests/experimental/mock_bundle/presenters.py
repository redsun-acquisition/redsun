from __future__ import annotations

from typing import Any

from psygnal import Signal

from redsun.experimental import (
    DeviceMapping,
    DocumentCallbacks,
    VirtualContainer,
    provides,
    slot,
)

from .keys import Calibration, Readings


class MockMotorPresenter:
    """Presenter sharing a value it computes from its devices.

    Asks for the device map and for a service the bundle's own provider
    supplies, so a config-driven session exercises both routes.
    """

    sig_moved = Signal(str, float)

    def __init__(
        self,
        name: str,
        /,
        devices: DeviceMapping,
        calibration: Calibration,
        step: float = 1.0,
    ) -> None:
        self.name = name
        self.devices = devices
        self.calibration = calibration
        self.step = step

    @provides
    def readings(self) -> Readings:
        return Readings({name: self.step * self.calibration for name in self.devices})

    @slot
    def move(self, axis: str, amount: float) -> None:
        self.moved = (axis, amount)


class MockLatePresenter:
    """Presenter reading a registry that other components fill after it.

    Holds the live view rather than copying it, which is what makes the
    component independent of the order it was built in.
    """

    def __init__(self, name: str, /, callbacks: DocumentCallbacks) -> None:
        self.name = name
        self.callbacks = callbacks

    @property
    def seen(self) -> dict[str, Any]:
        return dict(self.callbacks)


class MockRegistrar:
    """Presenter registering a document callback while it is built."""

    def __init__(self, name: str, /, virtual: VirtualContainer) -> None:
        self.name = name
        virtual.register_callbacks(self, name=name)

    def __call__(self, name: str, doc: Any) -> None:
        self.last = name
