# SPDX-License-Identifier: Apache-2.0
# The design of this module is heavily inspired by ophyd-async
# (https://github.com/bluesky/ophyd-async), developed by the Bluesky collaboration.
# ophyd-async is licensed under the BSD 3-Clause License.
# No source code from ophyd-async has been copied; the architectural patterns
# (shared writer, FrameSink, SourceInfo, stream document generation) were
# studied and independently re-implemented to fit the redsun model.

"""Abstract base classes for storage writers."""

from __future__ import annotations

import abc
import threading as th
import uuid
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypeVar

from redsun.log import Loggable

if TYPE_CHECKING:
    from collections.abc import Iterator

    import numpy as np
    import numpy.typing as npt
    from bluesky.protocols import StreamAsset
    from event_model.documents import StreamDatum, StreamResource


@dataclass
class SourceInfo:
    """Metadata for a registered data source.

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
    mimetype : str
        MIME type hint for the storage backend.
    frames_written : int
        Running count of frames written so far.
    collection_counter : int
        Frames reported in the current collection cycle.
    stream_resource_uid : str
        UID of the current `StreamResource` document.
    extra : dict[str, Any]
        Optional extra metadata for backend-specific use (e.g. OME-Zarr
        axis labels, physical units).  Base [`Writer`][redsun.storage.Writer]
        ignores this field; specialised subclasses may read it.
    """

    name: str
    dtype: np.dtype[np.generic]
    shape: tuple[int, ...]
    data_key: str
    mimetype: str = "application/octet-stream"
    frames_written: int = 0
    collection_counter: int = 0
    stream_resource_uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    extra: dict[str, Any] = field(default_factory=dict)


class FrameSink:
    """Device-facing handle for pushing frames to a storage backend.

    Returned by [`Writer.prepare`][redsun.storage.Writer.prepare].
    Devices write frames by calling [`write`][redsun.storage.FrameSink.write];
    the sink routes each frame to the correct array inside the shared
    [`Writer`][redsun.storage.Writer] and updates the frame counter atomically.

    Calling [`close`][redsun.storage.FrameSink.close] is equivalent to calling
    [`Writer.complete`][redsun.storage.Writer.complete] for this source — it
    signals that no more frames will arrive and triggers backend finalisation
    once all active sinks have been closed.

    Parameters
    ----------
    writer : Writer
        The shared writer that owns this sink.
    name : str
        Source name this sink is bound to.
    """

    def __init__(self, writer: Writer, name: str) -> None:
        self._writer = writer
        self._name = name

    def write(self, frame: npt.NDArray[np.generic]) -> None:
        """Push *frame* to the storage backend.

        Thread-safe; multiple sinks may call `write` concurrently.

        Parameters
        ----------
        frame : npt.NDArray[np.generic]
            Array data to write.  dtype and shape must match the source
            registration from [`Writer.update_source`][redsun.storage.Writer.update_source].
        """
        with self._writer._lock:
            self._writer._write_frame(self._name, frame)
            self._writer._sources[self._name].frames_written += 1

    def close(self) -> None:
        """Signal that no more frames will be written from this sink.

        Delegates to [`Writer.complete`][redsun.storage.Writer.complete].
        The backend is finalised once all active sinks have called `close`.
        """
        self._writer.complete(self._name)


_W = TypeVar("_W", bound="Writer")


class Writer(abc.ABC, Loggable):
    """Abstract base class for data writers.

    This interface loosely follows the Bluesky `Flyable` protocol while
    remaining generic — methods do not need to return a `Status` object;
    that is left to the device that owns the writer.

    A single `Writer` instance is shared by all devices in a session.
    Each device registers itself as a *source* via
    [`update_source`][redsun.storage.Writer.update_source] and obtains
    a dedicated [`FrameSink`][redsun.storage.FrameSink] via
    [`prepare`][redsun.storage.Writer.prepare].

    Call order per acquisition:

    1. `update_source(name, dtype, shape)` — register the device
    2. `prepare(name, capacity)` — returns a [`FrameSink`][redsun.storage.FrameSink]
    3. `kickoff()` — opens the backend
    4. `sink.write(frame)` — push frames (thread-safe)
    5. `sink.close()` — signals completion (calls [`complete`][redsun.storage.Writer.complete])

    Subclasses must implement:

    - [`mimetype`][redsun.storage.Writer.mimetype] — MIME type string for this backend
    - [`prepare`][redsun.storage.Writer.prepare] — source-specific setup; must call `super().prepare()`
    - [`kickoff`][redsun.storage.Writer.kickoff] — open the backend; must call `super().kickoff()`
    - `_write_frame` — write one frame to the backend
    - `_finalize` — close the backend when all sources are complete

    Parameters
    ----------
    name : str
        Unique name for this writer instance (used for logging).
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._store_path = ""
        self._lock = th.Lock()
        self._is_open = False
        self._sources: dict[str, SourceInfo] = {}
        self._active_sinks: set[str] = set()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        """Return whether the writer is currently open."""
        return self._is_open

    @property
    def name(self) -> str:
        """Return the name of this writer."""
        return self._name

    @property
    @abc.abstractmethod
    def mimetype(self) -> str:
        """Return the MIME type string for this backend."""
        ...

    @property
    def sources(self) -> MappingProxyType[str, SourceInfo]:
        """Return a read-only view of the registered data sources."""
        return MappingProxyType(self._sources)

    # ------------------------------------------------------------------
    # Source management
    # ------------------------------------------------------------------

    def update_source(
        self,
        name: str,
        dtype: np.dtype[np.generic],
        shape: tuple[int, ...],
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Register or update a data source.

        Parameters
        ----------
        name : str
            Source name (typically the device name).
        dtype : np.dtype[np.generic]
            NumPy data type of the frames.
        shape : tuple[int, ...]
            Shape of individual frames.
        extra : dict[str, Any] | None
            Optional backend-specific metadata forwarded to
            [`SourceInfo`][redsun.storage.SourceInfo].

        Raises
        ------
        RuntimeError
            If the writer is currently open.
        """
        if self._is_open:
            raise RuntimeError("Cannot update sources while writer is open.")

        data_key = f"{name}:buffer:stream"
        self._sources[name] = SourceInfo(
            name=name,
            dtype=dtype,
            shape=shape,
            data_key=data_key,
            mimetype=self.mimetype,
            extra=extra or {},
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

    # ------------------------------------------------------------------
    # Acquisition lifecycle
    # ------------------------------------------------------------------

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
        self._active_sinks.add(name)
        return FrameSink(self, name)

    def complete(self, name: str) -> None:
        """Mark acquisition complete for *name*.

        Called automatically by [`FrameSink.close`][redsun.storage.FrameSink.close].
        The backend is finalised once all active sinks have called `close`.

        Parameters
        ----------
        name : str
            Source name.
        """
        self._active_sinks.discard(name)
        if not self._active_sinks:
            self._finalize()
            self._is_open = False

    # ------------------------------------------------------------------
    # Backend hooks (subclass responsibility)
    # ------------------------------------------------------------------

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
        """Close the backend after all sinks have been closed."""
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
                "mimetype": source.mimetype,
                "parameters": {"array_name": source.name},
                "uid": source.stream_resource_uid,
                "uri": self._store_path,
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
