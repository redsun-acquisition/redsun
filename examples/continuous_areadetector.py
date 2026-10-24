"""The areaDetector session of "How to write a camera for continuous acquisition"."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003
from typing import Annotated

import numpy as np
from ophyd_async.core import AsyncStatus, PathProvider, set_and_wait_for_value
from ophyd_async.epics.adcore import (
    ADImageMode,
    ADWriterFactory,
    ContAcqDetector,
    PluginSignalDataLogic,
)
from ophyd_async.epics.core import epics_signal_r

from docs.examples.continuous_camera import LiveFrames, hinted_arrays
from redsun import AsDevice, AsPresenter, AsService, Attach, Declare, Link
from redsun.qt import QtSession


# --8<-- [start:camera]
class SimCamera(ContAcqDetector):
    """An areaDetector camera that acquires continuously."""

    def __init__(
        self, prefix: str, path_provider: PathProvider, name: str = ""
    ) -> None:
        self.image = epics_signal_r(np.ndarray, f"pva://{prefix}Pva1:Image")
        super().__init__(prefix, ADWriterFactory.hdf(path_provider), name=name)
        self.add_detector_logics(PluginSignalDataLogic(self.driver, self.image))

    @AsyncStatus.wrap
    async def stage(self) -> None:
        self.was_acquiring = await self.driver.acquire.get_value()
        if not self.was_acquiring:
            await self.driver.image_mode.set(ADImageMode.CONTINUOUS)
            # in continuous mode the put completes only when acquisition stops
            await set_and_wait_for_value(
                self.driver.acquire, True, wait_for_set_completion=False
            )
        await super().stage()

    @AsyncStatus.wrap
    async def unstage(self) -> None:
        await super().unstage()
        if not self.was_acquiring:
            await self.driver.acquire.set(False)


# --8<-- [end:camera]
# --8<-- [start:session]
class MyApp(QtSession):
    detector_ioc: Annotated[AsService, Attach("SIM:")]
    camera: Annotated[AsDevice[SimCamera], Declare(service="detector_ioc")]
    live: AsPresenter[LiveFrames]

    def wire(self) -> Iterator[Link]:
        for device in self.devices.values():
            for signal in hinted_arrays(device):
                yield signal, self.live.show


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
