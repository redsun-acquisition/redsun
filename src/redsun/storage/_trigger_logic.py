from __future__ import annotations

from typing import TYPE_CHECKING

from ophyd_async.core import DetectorTriggerLogic, TriggerInfo

from redsun.storage import SourceInfo

if TYPE_CHECKING:
    from redsun.storage import DataWriter


class WriterTriggerLogic(DetectorTriggerLogic):
    def __init__(self, writer: DataWriter) -> None:
        self._writer = writer

    async def prepare_internal(
        self, num: int, livetime: float, deadtime: float
    ) -> None: ...

    async def default_trigger_info(self) -> TriggerInfo:
        return TriggerInfo(number_of_events=0)

    def update_source(
        self,
        datakey_name: str,
        dtype_numpy: str,
        shape: tuple[int, ...],
        capacity: int | None = None,
    ) -> None:
        """Update the data source information for a given data key.

        Parameters
        ----------
        datakey_name : str
            The name of the data key to update.
        dtype_numpy : str
            The NumPy data type as a string for the source frames.
        shape : tuple[int, ...]
            The shape of individual frames from the source.
        capacity : int | None
            The maximum number of frames to accept.

            Defaults to None (unlimited).
        """
        self._writer.register(
            datakey_name,
            SourceInfo(dtype_numpy=dtype_numpy, shape=shape, capacity=capacity),
        )

    @property
    def writer(self) -> DataWriter:
        """The data writer used by this trigger logic."""
        return self._writer
