from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ophyd_async.core import DetectorTriggerLogic, TriggerInfo

from redsun.storage import SourceInfo

if TYPE_CHECKING:
    from redsun.storage import DataWriter
    from redsun.storage.logics._common import NDArrayInfo


@dataclass
class FrameWriterTriggerLogic(DetectorTriggerLogic):
    """Trigger logic for writing 2D frames."""

    datakey_name: str
    """The name of the data key to write frames to."""

    writer: DataWriter
    """The data writer to use for this logic."""

    info: NDArrayInfo
    """Array information for the source frames."""

    async def prepare_internal(
        self, num: int, livetime: float, deadtime: float
    ) -> None:
        x, y, height, width, np_dtype = await asyncio.gather(
            self.info.x.get_value(),
            self.info.y.get_value(),
            self.info.height.get_value(),
            self.info.width.get_value(),
            self.info.numpy_dtype.get_value(),
        )
        actual_shape = (height - y, width - x)
        self.writer.register(
            self.datakey_name,
            SourceInfo(dtype_numpy=np_dtype, shape=actual_shape, capacity=num),
        )

    async def default_trigger_info(self) -> TriggerInfo:
        return TriggerInfo(number_of_events=0)
