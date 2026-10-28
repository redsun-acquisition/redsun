"""The session of the guide "How to serve a FastCS controller over sharedbox"."""

from __future__ import annotations

from collections.abc import Mapping  # noqa: TC003
from typing import Annotated, Any, ClassVar

from ophyd_async.core import Device, SignalR, SignalRW, TriggerableCommand

from redsun import AsDevice, AsService, Declare, Launch
from redsun.device.sharedbox import BoxDeviceConnector, BoxPutError, stream_name
from redsun.qt import QtSession


# --8<-- [start:device]
class MyDetector(Device):
    exposure: SignalRW[float]
    state: SignalR[str]
    start: TriggerableCommand

    def __init__(self, prefix: str, name: str = "") -> None:
        # --8<-- [start:stream]
        self.counts_stream = stream_name(prefix, "counts")
        # --8<-- [end:stream]
        super().__init__(name=name, connector=BoxDeviceConnector(prefix))


# --8<-- [end:device]
# --8<-- [start:refused]
async def try_exposure(detector: MyDetector, value: float) -> bool:
    try:
        await detector.exposure.set(value)
    except BoxPutError as error:
        print(f"{error.attribute} refused {value}: {error}")
        return False
    return True


# --8<-- [end:refused]
# --8<-- [start:session]
class MyApp(QtSession):
    config: ClassVar[Mapping[str, Any]] = {"services": {"transport": "sharedbox"}}

    detector_service: Annotated[
        AsService, Launch("box_service", ready="detector ready", prefix="MYAPP:DET")
    ]
    detector: Annotated[AsDevice[MyDetector], Declare(service="detector_service")]


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
