from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ophyd_async.core import DetectorArmLogic

if TYPE_CHECKING:
    from redsun.storage import DataWriter


@dataclass
class FrameWriterArmLogic(DetectorArmLogic):
    datakey_name: str
    """The name of the data key to write frames to."""

    writer: DataWriter

    async def arm(self) -> None:
        if not self.writer.is_open:
            self.writer.open()

    async def wait_for_idle(self) -> None:
        pass

    async def disarm(self) -> None:
        if self.writer.is_open:
            self.writer.unregister(self.datakey_name)
            if len(self.writer.sources) == 0:
                self.writer.close()
