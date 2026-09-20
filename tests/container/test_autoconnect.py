"""The build connects devices before any presenter is built, and skips those that fail."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pytest
from ophyd_async.core import Device, DeviceConnector, NotConnectedError

from redsun.containers import (
    AppContainer,
    declare_device,
    declare_presenter,
    declare_service,
)
from redsun.containers import container as container_module
from redsun.presenter import Presenter

if TYPE_CHECKING:
    from collections.abc import Mapping


class CountingConnector(DeviceConnector):
    def __init__(self) -> None:
        self.real = 0
        self.mock = 0

    async def connect_real(
        self, device: Device, timeout: float, force_reconnect: bool
    ) -> None:
        self.real += 1

    async def connect_mock(self, device: Device, mock: Any) -> None:
        self.mock += 1


class RefusingConnector(DeviceConnector):
    async def connect_real(
        self, device: Device, timeout: float, force_reconnect: bool
    ) -> None:
        raise NotConnectedError("the camera did not answer")


class CountedDevice(Device):
    def __init__(self, name: str = "") -> None:
        self.connector = CountingConnector()
        super().__init__(name=name, connector=self.connector)


class RefusingDevice(Device):
    def __init__(self, prefix: str = "", name: str = "") -> None:
        super().__init__(name=name, connector=RefusingConnector())


class DeviceWithAutoconnectKeyword(Device):
    def __init__(self, name: str = "", autoconnect: bool = False) -> None:
        super().__init__(name=name)


class ConnectionsSeen(Presenter):
    """Records, as it is built, how often each device it received was connected."""

    def __init__(
        self, name: str, devices: Mapping[str, Device], /, **kwargs: Any
    ) -> None:
        super().__init__(name, devices)
        self.seen = {
            device_name: device.connector.real
            for device_name, device in devices.items()
            if isinstance(device, CountedDevice)
        }


def test_the_build_connects_each_device_before_presenters_are_built() -> None:
    class App(AppContainer):
        motor = declare_device(CountedDevice)
        stage = declare_device(CountedDevice, autoconnect=True)
        watcher = declare_presenter(ConnectionsSeen)

    app = App().build()

    watcher = app.presenters["watcher"]
    assert isinstance(watcher, ConnectionsSeen)
    assert watcher.seen == {"motor": 1, "stage": 1}


def test_a_device_without_autoconnect_is_left_for_connect_devices() -> None:
    """connect_devices connects every device, whatever autoconnect says."""

    class App(AppContainer):
        motor = declare_device(CountedDevice, autoconnect=False)

    app = App().build()
    motor = app.devices["motor"]
    assert isinstance(motor, CountedDevice)
    assert motor.connector.real == 0

    app.connect_devices()

    assert motor.connector.real == 1


def test_a_device_that_does_not_connect_is_skipped_and_named(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class App(AppContainer):
        camera = declare_device(RefusingDevice)
        motor = declare_device(CountedDevice)
        watcher = declare_presenter(ConnectionsSeen)

    app = App().build()

    assert set(app.devices) == {"motor"}
    watcher = app.presenters["watcher"]
    assert isinstance(watcher, ConnectionsSeen)
    assert watcher.seen == {"motor": 1}
    messages = [r.getMessage() for r in caplog.records]
    assert "Failed to connect device 'camera': the camera did not answer" in messages
    (closing,) = [m for m in messages if "Not built:" in m]
    assert closing.endswith("Not built: camera (device, not connected)")


def test_a_device_whose_attached_service_does_not_answer_names_it(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The message names the service and the time it was given."""
    monkeypatch.setattr(container_module, "CONNECT_TIMEOUT", 0.5)

    class App(AppContainer):
        beamline = declare_service(prefix="BL01:")
        camera = declare_device(RefusingDevice, service="beamline")

    app = App().build()

    assert app.devices == {}
    (failure,) = [
        r.getMessage()
        for r in caplog.records
        if r.getMessage().startswith("Failed to connect device 'camera'")
    ]
    assert "service 'beamline' (attached) did not answer within 0.5 s" in failure


@pytest.mark.parametrize(
    ("cls", "kwargs", "reason"),
    [
        (CountedDevice, {"autoconnect": "yes"}, "takes true or false"),
        (DeviceWithAutoconnectKeyword, {"autoconnect": True}, "'autoconnect' keyword"),
    ],
    ids=["not-a-bool", "own-keyword"],
)
def test_an_autoconnect_the_container_cannot_read_is_refused(
    cls: type[Device], kwargs: dict[str, Any], reason: str
) -> None:
    with pytest.raises(TypeError, match=reason):

        class App(AppContainer):
            device = declare_device(cls, **kwargs)


def test_connect_devices_in_mock_mode_connects_every_device(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class App(AppContainer):
        motor = declare_device(CountedDevice, autoconnect=False)

    app = App().build()
    app.connect_devices(mock=True)

    motor = app.devices["motor"]
    assert isinstance(motor, CountedDevice)
    assert (motor.connector.real, motor.connector.mock) == (0, 1)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
