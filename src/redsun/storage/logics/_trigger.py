from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ophyd_async.core import DetectorTriggerLogic, TriggerInfo

from redsun.storage import SourceInfo

if TYPE_CHECKING:
    import numpy as np
    from ophyd_async.core import SignalRW

    from redsun.storage import DataWriter


@dataclass
class FrameWriterTriggerLogic(DetectorTriggerLogic):
    """Trigger logic for writing 2D frames."""

    datakey_name: str
    """The name of the data key to write frames to."""

    writer: DataWriter
    """The data writer to use for this logic."""

    shape: SignalRW[np.ndarray[tuple[int, ...], np.dtype[np.uint64]]]
    """Shape of the source frames, formmated as (x, y, height, width)."""

    numpy_dtype: SignalRW[str]
    """NumPy data type as a string for the source frames."""

    async def prepare_internal(
        self, num: int, livetime: float, deadtime: float
    ) -> None:
        shape_array, np_dtype = await asyncio.gather(
            self.shape.get_value(), self.numpy_dtype.get_value()
        )
        shape: tuple[int, ...] = tuple(shape_array.tolist())
        if len(shape) != 4:
            raise ValueError(f"Expected shape array of length 4, got {len(shape)}")
        actual_shape = (shape[2] - shape[0], shape[3] - shape[1])
        self.writer.register(
            self.datakey_name,
            SourceInfo(dtype_numpy=np_dtype, shape=actual_shape, capacity=num),
        )

    async def default_trigger_info(self) -> TriggerInfo:
        return TriggerInfo(number_of_events=0)
