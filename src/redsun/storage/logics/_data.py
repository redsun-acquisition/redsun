from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from ophyd_async.core import (
    DetectorDataLogic,
    StreamResourceDataProvider,
    StreamResourceInfo,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ophyd_async.core import PathProvider, StreamableDataProvider

    from redsun.storage._base import DataWriter


@dataclass
class FrameWriterDataLogic(DetectorDataLogic):
    """Data logic that writes frames to a data writer."""

    writer: DataWriter
    """The data writer to use for this logic."""

    path_provider: PathProvider
    """Path provider to use for generating output file paths."""

    def get_hinted_fields(self, datakey_name: str) -> Sequence[str]:
        return [datakey_name]

    async def prepare_unbounded(self, datakey_name: str) -> StreamableDataProvider:
        path_info = self.path_provider(datakey_name)
        extension = self.writer.file_extension
        if not self.writer.is_path_set():
            write_path = path_info.directory_path / ".".join(
                [path_info.filename, extension]
            )
            self.writer.set_store_path(write_path)

        shape = self.writer.sources[datakey_name].shape
        capacity = self.writer.sources[datakey_name].capacity
        dtype_numpy = np.dtype(self.writer.sources[datakey_name].dtype_numpy).str

        data_resource = StreamResourceInfo(
            data_key=datakey_name,
            shape=(capacity, *shape),
            chunk_shape=shape,
            dtype_numpy=dtype_numpy,
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
