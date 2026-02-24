"""Abstract base classes for storage writers."""

from __future__ import annotations

import abc
import threading as th
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeVar

from redsun.log import Loggable

if TYPE_CHECKING:
    from collections.abc import Iterator

    import numpy as np
    import numpy.typing as npt
    from bluesky.protocols import StreamAsset
    from event_model.documents import StreamDatum, StreamResource

    from redsun.storage._prepare import StorageInfo


@dataclass
class SourceInfo:
    """Runtime acquisition state for a registered data source.

    Tracks per-source counters and identifiers used during an acquisition.
    Format and metadata are carried by
    [`DeviceStorageInfo`][redsun.storage.DeviceStorageInfo] in
    [`StorageInfo.devices`][redsun.storage.StorageInfo]; this dataclass
    is internal to [`Writer`][redsun.storage.Writer].

    Attributes
    ----------
    name : str
        Name of the data source (e.g. the device name).
    dtype : np.dtype[np.generic]
        NumPy data type of the source frames.
    shape : tuple[int, ...]
        Shape of individual frames from the source.
    data_key : str
        Bluesky data key for stream documents.
    frames_written : int
        Running count of frames written so far.
    collection_counter : int
        Frames reported in the current collection cycle.
    stream_resource_uid : str
        UID of the current `StreamResource` document.
    """

    name: str
    dtype: np.dtype[np.generic]
    shape: tuple[int, ...]
    data_key: str
    frames_written: int = 0
    collection_counter: int = 0
    stream_resource_uid: str = field(default_factory=lambda: str(uuid.uuid4()))


class FrameSink:
    """Device-facing handle for pushing frames to a storage backend.

    Returned by [`Writer.prepare`][redsun.storage.Writer.prepare].
    Devices write frames by calling [`write`][redsun.storage.FrameSink.write];
    the sink routes each frame to the backend and updates the frame counter
    atomically.

    Calling [`close`][redsun.storage.FrameSink.close] signals that no more
    frames will arrive and triggers backend finalisation.

    Parameters
    ----------
    writer : Writer
        The writer that owns this sink.
    name : str
        Source name this sink is bound to.
    """

    def __init__(self, writer: Writer, name: str) -> None:
        self._writer = writer
        self._name = name

    def write(self, frame: npt.NDArray[np.generic]) -> None:
        """Push `frame` to the storage backend.

        Thread-safe.

        Parameters
        ----------
        frame : npt.NDArray[np.generic]
            Array data to write. dtype and shape must match the source
            registration from [`Writer.update_source`][redsun.storage.Writer.update_source].
        """
        with self._writer._lock:
            self._writer._write_frame(self._name, frame)
            self._writer._sources[self._name].frames_written += 1

    def close(self) -> None:
        """Signal that no more frames will be written from this sink.

        Delegates to [`Writer.complete`][redsun.storage.Writer.complete].
        """
        self._writer.complete(self._name)


_W = TypeVar("_W", bound="Writer")


class Writer(abc.ABC, Loggable):
    """Abstract base class for data writers.

    Each device that writes data owns its own `Writer` instance,
    constructed from a [`StorageInfo`][redsun.storage.StorageInfo]
    received via `prepare()`. The writer is responsible for a single
    store at a single URI.

    Call order per acquisition:

    1. `update_source(name, data_key, dtype, shape)` — register the device source
    2. `prepare(name, capacity)` — returns a [`FrameSink`][redsun.storage.FrameSink]
    3. `kickoff()` — opens the backend
    4. `sink.write(frame)` — push frames (thread-safe)
    5. `sink.close()` — signals completion

    Subclasses must implement:

    - [`mimetype`][redsun.storage.Writer.mimetype] — MIME type string for this backend
    - [`prepare`][redsun.storage.Writer.prepare] — source-specific setup; must call `super().prepare()`
    - [`kickoff`][redsun.storage.Writer.kickoff] — open the backend; must call `super().kickoff()`
    - `_write_frame` — write one frame to the backend
    - `_finalize` — close the backend

    Parameters
    ----------
    info : StorageInfo
        Fully resolved storage location. The URI and device metadata
        are read from this object on construction.
    """

    def __init__(self, info: StorageInfo) -> None:
        self.info = info
        self._lock = th.Lock()
        self._is_open = False
        self._sources: dict[str, SourceInfo] = {}

    @property
    def is_open(self) -> bool:
        """Return whether the writer is currently open."""
        return self._is_open

    @property
    def uri(self) -> str:
        """Return the URI for this writer."""
        return self.info.uri

    @property
    @abc.abstractmethod
    def mimetype(self) -> str:
        """Return the MIME type string for this backend."""
        ...

    def update_source(
        self,
        name: str,
        data_key: str,
        dtype: np.dtype[np.generic],
        shape: tuple[int, ...],
    ) -> None:
        """Register or update a data source.

        Parameters
        ----------
        name : str
            Source name (typically the device name).
        data_key : str
            Bluesky data key for stream documents.
        dtype : np.dtype[np.generic]
            NumPy data type of the frames.
        shape : tuple[int, ...]
            Shape of each frame.

        Raises
        ------
        RuntimeError
            If the writer is currently open.
        """
        if self._is_open:
            raise RuntimeError("Cannot update sources while writer is open.")
        self._sources[name] = SourceInfo(
            name=name,
            dtype=dtype,
            shape=shape,
            data_key=data_key,
        )
        self.logger.debug(f"Updated source '{name}' with shape {shape}")

    def clear_source(self, name: str, *, raise_if_missing: bool = False) -> None:
        """Remove a registered data source.

        Parameters
        ----------
        name : str
            Source name to remove.
        raise_if_missing : bool
            If `True`, raise `KeyError` when the source is absent.

        Raises
        ------
        RuntimeError
            If the writer is currently open.
        KeyError
            If *raise_if_missing* is `True` and the source is absent.
        """
        if self._is_open:
            raise RuntimeError("Cannot clear sources while writer is open.")

        try:
            del self._sources[name]
            self.logger.debug(f"Cleared source '{name}'")
        except KeyError as exc:
            self.logger.error(f"Source '{name}' not found.")
            if raise_if_missing:
                raise exc

    def get_indices_written(self, name: str | None = None) -> int:
        """Return the number of frames written for a source.

        Parameters
        ----------
        name : str | None
            Source name.  If `None`, returns the minimum across all
            sources (useful for synchronisation checks).

        Raises
        ------
        KeyError
            If *name* is not registered.
        """
        if name is None:
            if not self._sources:
                return 0
            return min(s.frames_written for s in self._sources.values())

        if name not in self._sources:
            raise KeyError(f"Unknown source '{name}'")
        return self._sources[name].frames_written

    def reset_collection_state(self, name: str) -> None:
        """Reset the collection counter for a new acquisition.

        Parameters
        ----------
        name : str
            Source name to reset.
        """
        source = self._sources[name]
        source.collection_counter = 0
        source.stream_resource_uid = str(uuid.uuid4())

    @abc.abstractmethod
    def kickoff(self) -> None:
        """Open the storage backend for a new acquisition.

        Subclasses must call `super().kickoff()` to set
        [`is_open`][redsun.storage.Writer.is_open].
        Subsequent calls while already open must be no-ops.
        """
        if not self._is_open:
            self._is_open = True

    @abc.abstractmethod
    def prepare(self, name: str, capacity: int = 0) -> FrameSink:
        """Prepare storage for a specific source and return a frame sink.

        Called once per device per acquisition.  Resets per-source counters
        and returns a [`FrameSink`][redsun.storage.FrameSink] bound to *name*.

        Parameters
        ----------
        name : str
            Source name.
        capacity : int
            Maximum frames to accept (`0` = unlimited).

        Returns
        -------
        FrameSink
            Bound sink; call `sink.write(frame)` to push frames.

        Raises
        ------
        KeyError
            If *name* has not been registered via
            [`update_source`][redsun.storage.Writer.update_source].
        """
        source = self._sources[name]
        source.frames_written = 0
        source.collection_counter = 0
        source.stream_resource_uid = str(uuid.uuid4())
        return FrameSink(self, name)

    def complete(self, name: str) -> None:
        """Mark acquisition complete for *name* and finalise the backend.

        Called automatically by [`FrameSink.close`][redsun.storage.FrameSink.close].

        Parameters
        ----------
        name : str
            Source name.
        """
        self._sources.pop(name, None)
        if not self._sources:
            self._finalize()
            self._is_open = False

    @abc.abstractmethod
    def _write_frame(self, name: str, frame: npt.NDArray[np.generic]) -> None:
        """Write one frame to the backend.

        Called by [`FrameSink.write`][redsun.storage.FrameSink.write]
        under the writer lock.

        Parameters
        ----------
        name : str
            Source name.
        frame : npt.NDArray[np.generic]
            Frame data to write.
        """
        ...

    @abc.abstractmethod
    def _finalize(self) -> None:
        """Close the backend after the source has completed."""
        ...

    # ------------------------------------------------------------------
    # Stream document generation
    # ------------------------------------------------------------------

    def collect_stream_docs(
        self,
        name: str,
        indices_written: int,
    ) -> Iterator[StreamAsset]:
        """Yield `StreamResource` and `StreamDatum` documents for *name*.

        Parameters
        ----------
        name : str
            Source name.
        indices_written : int
            Number of frames to report in this call.

        Yields
        ------
        StreamAsset
            Tuples of `("stream_resource", doc)` or `("stream_datum", doc)`.

        Raises
        ------
        KeyError
            If *name* is not registered.
        """
        if name not in self._sources:
            raise KeyError(f"Unknown source '{name}'")

        source = self._sources[name]

        if indices_written == 0:
            return

        frames_to_report = min(indices_written, source.frames_written)

        if source.collection_counter >= frames_to_report:
            return

        if source.collection_counter == 0:
            stream_resource: StreamResource = {
                "data_key": source.data_key,
                "mimetype": self.mimetype,
                "parameters": {"array_name": source.name},
                "uid": source.stream_resource_uid,
                "uri": self.uri,
            }
            yield ("stream_resource", stream_resource)

        stream_datum: StreamDatum = {
            "descriptor": "",
            "indices": {"start": source.collection_counter, "stop": frames_to_report},
            "seq_nums": {"start": 0, "stop": 0},
            "stream_resource": source.stream_resource_uid,
            "uid": f"{source.stream_resource_uid}/{source.collection_counter}",
        }
        yield ("stream_datum", stream_datum)

        source.collection_counter = frames_to_report
