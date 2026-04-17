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

    async def disarm(self) -> None:
        if self.writer.is_open:
            # unregister the source
            # for this datakey
            self.writer.unregister(self.datakey_name)

        # if there are no more sources,
        # we can close the writer
        if len(self.writer.sources) == 0:
            self.writer.close()
