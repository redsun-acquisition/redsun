from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ophyd_async.core import soft_signal_r_and_setter

if TYPE_CHECKING:
    from pathlib import PurePath
    from typing import Any

    import numpy.typing as npt
    from ophyd_async.core import SignalR


@dataclass
class SourceInfo:
    """Runtime acquisition state for a registered data source."""

    dtype_numpy: str
    """NumPy data type as string of the source frames."""

    shape: tuple[int, ...]
    """Shape of individual frames from the source."""

    capacity: int
    """Maximum frames to accept. 0 means unlimited."""


class DataWriter(abc.ABC):
    """Abstract base class for data writers.

    To be used in conjunction with ophyd-async logic
    composition.
    """

    def __init__(self) -> None:
        self._count_sig, self._update_count = soft_signal_r_and_setter(int)

    @property
    @abc.abstractmethod
    def is_open(self) -> bool:
        """Indicates whether the data writer is currently open."""
        ...

    @property
    @abc.abstractmethod
    def sources(self) -> dict[str, SourceInfo]:
        """Dictionary of registered data sources, keyed by source name."""
        ...

    @property
    @abc.abstractmethod
    def file_extension(self) -> str:
        """File extension to use for output files."""
        ...

    @property
    @abc.abstractmethod
    def mimetype(self) -> str:
        """MIME type to use for output files."""
        ...

    @property
    def image_counter(self) -> SignalR[int]:
        """Signal for the number of images written."""
        return self._count_sig

    @abc.abstractmethod
    def set_store_path(self, path: PurePath) -> None:
        """Set the directory path where output files should be written.

        Parameters
        ----------
        path : Path
            The directory path where output files should be written.
        """
        ...

    @abc.abstractmethod
    def is_path_set(self) -> bool:
        """Check if the store path has been set."""
        ...

    @abc.abstractmethod
    def open(self) -> None:
        """Open the data writer, preparing it for writing."""
        ...

    @abc.abstractmethod
    def register(self, datakey: str, info: SourceInfo) -> None:
        """Register a data source with the writer.

        Parameters
        ----------
        datakey : str
            Source key for the data to be registered.
        info : SourceInfo
            Information about the data source.
        """
        ...

    @abc.abstractmethod
    def unregister(self, datakey: str) -> None:
        """Unregister a data source from the writer.

        Parameters
        ----------
        datakey : str
            Source key for the data to be unregistered.
        """
        ...

    @abc.abstractmethod
    def write(self, datakey: str, data: npt.NDArray[Any]) -> None:
        """Write data to the store.

        Parameters
        ----------
        datakey : str
            Source key for the data.
        data : npt.NDArray[Any]
            The data to be written, as a NumPy array.
        """
        ...

    @abc.abstractmethod
    def close(self, reset_path: bool = False) -> None:
        """Close the data writer.

        Parameters
        ----------
        reset_path : bool, optional
            If True, also reset the store path to an unset state. Default is False.
        """
        ...
