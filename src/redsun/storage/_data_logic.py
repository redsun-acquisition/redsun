from __future__ import annotations

from typing import TYPE_CHECKING

from ophyd_async.core import (
    AutoIncrementFilenameProvider,
    DetectorDataLogic,
    StaticPathProvider,
    StreamResourceDataProvider,
    StreamResourceInfo,
)

from redsun.storage._base import SourceInfo

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from ophyd_async.core import StreamableDataProvider

    from redsun.storage._base import DataWriter


class WriterDataLogic(DetectorDataLogic):
    """Data logic that writes frames to a data writer.

    This is the default data logic for detectors with a configured
    data writer.  It simply forwards frames to the writer's `write`
    method, which is expected to handle buffering and storage.
    """

    def __init__(
        self, writer: DataWriter, directory_path: Path, base_filename: str
    ) -> None:
        self._writer = writer
        self._path_provider = StaticPathProvider(
            filename_provider=AutoIncrementFilenameProvider(base_filename),
            directory_path=directory_path,
        )

    def get_hinted_fields(self, datakey_name: str) -> Sequence[str]:
        return list(self._writer.sources.keys())

    async def prepare_unbounded(self, datakey_name: str) -> StreamableDataProvider:
        path_info = self._path_provider(datakey_name)
        write_path = path_info.directory_path / ".".join(
            [path_info.filename, self._writer.file_extension]
        )
        extension = self._writer.file_extension
        self._writer.open(write_path)

        shape = self._writer.sources[datakey_name].shape
        capacity = self._writer.sources[datakey_name].capacity

        data_resource = StreamResourceInfo(
            data_key=datakey_name,
            shape=(capacity, *shape),
            chunk_shape=shape,
            dtype_numpy=self._writer.sources[datakey_name].dtype_numpy,
            parameters={},
        )

        # TODO: this seems to be used primarely for
        # HDF5 files; maybe a custom provider could be
        # implemented for Zarr
        return StreamResourceDataProvider(
            uri=f"{path_info.directory_path}{path_info.filename}.{extension}",
            resources=[data_resource],
            mimetype=self._writer.mimetype,
            collections_written_signal=self._writer.image_counter,
        )

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
        info = SourceInfo(dtype_numpy=dtype_numpy, shape=shape, capacity=capacity)
        self._writer.register(datakey_name, info)

    @property
    def writer(self) -> DataWriter:
        """The data writer used by this data logic."""
        return self._writer
