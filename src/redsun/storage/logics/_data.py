from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ophyd_async.core import (
    DetectorDataLogic,
    StreamResourceDataProvider,
    StreamResourceInfo,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ophyd_async.core import PathProvider, StreamableDataProvider

    from redsun.storage._base import DataWriter
    from redsun.storage.logics._common import NDArrayInfo


@dataclass
class FrameWriterDataLogic(DetectorDataLogic):
    """Data logic that writes frames to a data writer."""

    writer: DataWriter
    """The data writer to use for this logic."""

    info: NDArrayInfo
    """Array information for the source frames."""

    path_provider: PathProvider
    """Path provider to use for generating output file paths."""

    def get_hinted_fields(self, datakey_name: str) -> Sequence[str]:
        return [datakey_name]

    async def prepare_unbounded(self, datakey_name: str) -> StreamableDataProvider:
        if not self.writer.is_path_set():
            path_info = self.path_provider(datakey_name)
            write_path = path_info.directory_path / ".".join(
                [path_info.filename, self.writer.file_extension]
            )
            extension = self.writer.file_extension
            self.writer.set_store_path(write_path)

        shape = self.writer.sources[datakey_name].shape
        capacity = self.writer.sources[datakey_name].capacity

        data_resource = StreamResourceInfo(
            data_key=datakey_name,
            shape=(capacity, *shape),
            chunk_shape=shape,
            dtype_numpy=self.writer.sources[datakey_name].dtype_numpy,
            parameters={},
        )

        # TODO: this seems to be used primarely for
        # HDF5 files; maybe a custom provider could be
        # implemented for Zarr
        return StreamResourceDataProvider(
            uri=f"{path_info.directory_path}{path_info.filename}.{extension}",
            resources=[data_resource],
            mimetype=self.writer.mimetype,
            collections_written_signal=self.writer.image_counter,
        )
