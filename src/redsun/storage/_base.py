"""Abstract base classes for storage writers."""

from __future__ import annotations

import abc
import threading as th
import time
import uuid
from typing import TYPE_CHECKING, TypeVar

from redsun.log import Loggable
from redsun.storage.metadata import clear_metadata, snapshot_metadata

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any

    import numpy as np
    import numpy.typing as npt
    from bluesky.protocols import StreamAsset
    from event_model import DataKey
    from event_model.documents import StreamDatum, StreamResource


class SourceInfo:
    """Runtime acquisition state for a registered data source.

    Tracks per-source counters and identifiers used during an acquisition.
    This class is internal to [`Writer`][redsun.storage.Writer].

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
    capacity : int
        Maximum frames to accept. ``0`` means unlimited.
    frames_written : int
        Running count of frames written so far.
    collection_counter : int
        Frames reported in the current collection cycle.
    stream_resource_uid : str
        UID of the current ``StreamResource`` document.
    """

    __slots__ = (
        "name",
        "dtype",
        "shape",
        "data_key",
        "capacity",
        "frames_written",
        "collection_counter",
        "stream_resource_uid",
    )

    def __init__(
        self,
        name: str,
        dtype: np.dtype[np.generic],
        shape: tuple[int, ...],
        data_key: str,
        capacity: int = 0,
    ) -> None:
        self.name = name
        self.dtype = dtype
        self.shape = shape
        self.data_key = data_key
        self.capacity = capacity
        self.frames_written: int = 0
        self.collection_counter: int = 0
        self.stream_resource_uid: str = str(uuid.uuid4())


_W = TypeVar("_W", bound="Writer")

#: Composite registry key: (group name, mimetype).
_WriterKey = tuple[str, str]


class Writer(abc.ABC, Loggable):
    """Abstract base class for storage backend writers.

    Writers are long-lived singletons, created once when the application
    starts and reused across every acquisition.  The class-level registry
    is keyed by a **composite key** ``(name, mimetype)`` where:

    - ``mimetype`` identifies the storage format and determines which
      ``Writer`` subclass handles serialisation (e.g.
      ``"application/x-zarr"`` maps to ``ZarrWriter``).
    - ``name`` is a **store group name** that distinguishes multiple
      independent stores that share the same format.  Use ``"default"``
      for the common single-store case.  This is *not* a device name —
      many devices may contribute sources to the same writer by
      referencing the same ``(name, mimetype)`` key.

    Call order per acquisition:

    1. ``set_uri(uri)``
        - called by a presenter before the plan
    2. ``register(source_name, dtype, shape, capacity)``
        - called by each device in its own ``prepare()``
    3. ``open(source_name)``
        - called by each device; backend opens on the first call
        - returns ``{source_name: DataKey(...)}``
    4. ``write_frame(source_name, frame)``
        - push frames (thread-safe)
    5. ``close()``
        - finalise and close backend; called once all devices are done

    Subclasses must implement:

    - [`_class_mimetype`][redsun.storage.Writer._class_mimetype]
    - [`_on_register`][redsun.storage.Writer._on_register]
        - backend-specific setup after a source is registered
    - [`_open_backend`][redsun.storage.Writer._open_backend]
        - physically open the backend (called once on first ``open()``)
    - [`_write_frame`][redsun.storage.Writer._write_frame]
        - write one frame to the backend
    - [`_close_backend`][redsun.storage.Writer._close_backend]
        - close the backend

    Parameters
    ----------
    name : str
        Store group name.  See class docstring for semantics.
    """

    _registry: dict[_WriterKey, "Writer"] = {}
    _registry_lock: th.Lock = th.Lock()

    def __init__(self, name: str) -> None:
        self._name = name
        self._uri: str = ""
        self._lock = th.Lock()
        self._is_open = False
        self._sources: dict[str, SourceInfo] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    @classmethod
    def get(cls: type[_W], name: str = "default") -> _W:
        """Return the singleton writer for *(name, cls.mimetype)*.

        Creates a new instance on first call; returns the existing one
        on every subsequent call for the same ``(name, mimetype)`` pair.

        Parameters
        ----------
        name : str
            Store group name.  Defaults to ``"default"``.

        Returns
        -------
        Writer
            Singleton instance for ``(name, cls.mimetype)``.

        Raises
        ------
        TypeError
            If the existing registry entry is not an instance of ``cls``.
        """
        key: _WriterKey = (name, cls._class_mimetype())
        with cls._registry_lock:
            if key not in cls._registry:
                cls._registry[key] = cls(name)
            instance = cls._registry[key]
        if not isinstance(instance, cls):
            raise TypeError(
                f"Registry entry for {key!r} is {type(instance).__name__!r}, "
                f"expected {cls.__name__!r}"
            )
        return instance

    @classmethod
    def release(cls, name: str = "default") -> None:
        """Remove the registry entry for *(name, cls.mimetype)*.

        Parameters
        ----------
        name : str
            Store group name.  Defaults to ``"default"``.
        """
        key: _WriterKey = (name, cls._class_mimetype())
        with cls._registry_lock:
            cls._registry.pop(key, None)

    @classmethod
    @abc.abstractmethod
    def _class_mimetype(cls) -> str:
        """Return the MIME type string for this subclass.

        Subclasses implement this as a one-liner::

            @classmethod
            def _class_mimetype(cls) -> str:
                return "application/x-zarr"
        """
        ...

    @property
    def is_open(self) -> bool:
        """Return whether the backend is currently open."""
        return self._is_open

    @property
    def uri(self) -> str:
        """The current store URI."""
        return self._uri

    @property
    def mimetype(self) -> str:
        """The MIME type string for this backend."""
        return self._class_mimetype()

    def set_uri(self, uri: str) -> None:
        """Update the store URI for the next acquisition.

        Parameters
        ----------
        uri : str
            New store URI (e.g. ``"file:///data/2026_02_25/scan_00001"``).

        Raises
        ------
        RuntimeError
            If the writer is currently open.
        """
        if self._is_open:
            raise RuntimeError(
                f"Cannot change URI on writer ({self._name!r}, {self.mimetype!r}) "
                "while it is open."
            )
        self._uri = uri
        self.logger.debug(f"URI updated to {uri!r}")

    def register(
        self,
        name: str,
        dtype: np.dtype[np.generic],
        shape: tuple[int, ...],
        capacity: int = 0,
    ) -> None:
        """Register a data source before :meth:`open` is called.

        Safe to call multiple times on the same source name — counters
        are reset on each call, making it suitable for repeated
        acquisitions without recreating the writer.

        Parameters
        ----------
        name : str
            Source name, typically the device name.
        dtype : np.dtype[np.generic]
            NumPy data type of the frames.
        shape : tuple[int, ...]
            Shape of each individual frame.
        capacity : int
            Maximum number of frames to accept.  ``0`` means unlimited.

        Raises
        ------
        RuntimeError
            If the writer is currently open.
        """
        if self._is_open:
            raise RuntimeError(
                f"Cannot register source {name!r} on writer "
                f"({self._name!r}, {self.mimetype!r}) while it is open."
            )
        self._sources[name] = SourceInfo(
            name=name,
            dtype=dtype,
            shape=shape,
            data_key=name,
            capacity=capacity,
        )
        self.logger.debug(
            f"Registered source {name!r} — shape={shape}, capacity={capacity}"
        )
        self._on_register(name)

    @abc.abstractmethod
    def _on_register(self, name: str) -> None:
        """Backend-specific hook called after a source is registered.

        Invoked at the end of :meth:`register` once
        ``self._sources[name]`` is fully populated.

        Parameters
        ----------
        name : str
            The source name just registered.
        """
        ...

    def open(
        self,
        name: str,
        exposures_per_event: int = 1,
    ) -> dict[str, DataKey]:
        """Open the backend (on first call) and return describe output.

        Uses dtype/shape pre-registered via :meth:`register` for *name*.
        Subsequent calls while already open are a no-op for the backend
        and simply return the DataKey dict for *name*.

        Parameters
        ----------
        name : str
            Source name as passed to :meth:`register`.
        exposures_per_event : int
            Number of hardware exposures per logical event.

        Returns
        -------
        dict[str, DataKey]
            Bluesky data-key descriptor for *name*.

        Raises
        ------
        KeyError
            If *name* has not been registered.
        RuntimeError
            If :attr:`uri` has not been set.
        """
        if name not in self._sources:
            raise KeyError(f"Source {name!r} not registered. Call register() first.")
        if not self._is_open:
            if not self._uri:
                clear_metadata()
                raise RuntimeError(
                    f"Writer ({self._name!r}, {self.mimetype!r}) has no URI. "
                    "A presenter must call set_uri() before open()."
                )
            self._metadata = snapshot_metadata()
            self._is_open = True
            self._open_backend()
        source = self._sources[name]
        data_key: DataKey = {
            "source": self._uri,
            "dtype": "array",
            "shape": list(source.shape),
            "external": "STREAM:",
        }
        return {name: data_key}

    @abc.abstractmethod
    def _open_backend(self) -> None:
        """Physically open the storage backend.

        Called once by :meth:`open` when the first source is opened.
        Subclasses implement stream/file creation here.
        """
        ...

    def write_frame(self, name: str, frame: npt.NDArray[np.generic]) -> None:
        """Push one frame for *name* to the backend (thread-safe).

        Parameters
        ----------
        name : str
            Source name.
        frame : npt.NDArray[np.generic]
            Array data to write.
        """
        with self._lock:
            self._write_frame(name, frame)
            self._sources[name].frames_written += 1

    @abc.abstractmethod
    def _write_frame(self, name: str, frame: npt.NDArray[np.generic]) -> None:
        """Write one frame to the backend (called under lock).

        Parameters
        ----------
        name : str
            Source name.
        frame : npt.NDArray[np.generic]
            Frame data to write.
        """
        ...

    def get_indices_written(self, name: str | None = None) -> int:
        """Return the number of frames written for a source.

        Parameters
        ----------
        name : str | None
            Source name.  If ``None``, returns the minimum across all
            registered sources (useful for synchronisation checks).

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
            raise KeyError(f"Unknown source {name!r}")
        return self._sources[name].frames_written

    def observe_indices_written(
        self,
        timeout: float,
        *,
        name: str | None = None,
    ) -> Iterator[int]:
        """Yield the running frame count as frames are written.

        Parameters
        ----------
        timeout : float
            Maximum seconds to wait for the next new frame before raising.
        name : str | None
            Source name to observe.  ``None`` observes the minimum across
            all registered sources.

        Yields
        ------
        int
            Running total of frames written.

        Raises
        ------
        TimeoutError
            If no new frames arrive within *timeout* seconds.
        """
        deadline = time.monotonic() + timeout
        last = self.get_indices_written(name)
        while True:
            current = self.get_indices_written(name)
            if current != last:
                yield current
                last = current
                deadline = time.monotonic() + timeout
            if time.monotonic() > deadline:
                label = name if name is not None else "<all>"
                raise TimeoutError(f"No new frames from {label!r} within {timeout}s")
            time.sleep(0.01)

    def close(self) -> None:
        """Finalise and close the storage backend.

        Flushes any remaining state, calls :meth:`_close_backend`, resets
        ``is_open``, and clears acquisition metadata.  The writer instance
        remains in the registry and is ready for the next acquisition.
        """
        if not self._is_open:
            return
        self._close_backend()
        self._is_open = False
        clear_metadata()
        self.logger.debug("Backend closed.")

    @abc.abstractmethod
    def _close_backend(self) -> None:
        """Close the storage backend.

        Called by :meth:`close` after all sources are done.
        """
        ...

    def reset_collection_state(self, name: str) -> None:
        """Reset the stream-document counters for *name*.

        Parameters
        ----------
        name : str
            Source name to reset.
        """
        source = self._sources[name]
        source.collection_counter = 0
        source.stream_resource_uid = str(uuid.uuid4())

    def clear_sources(self) -> None:
        """Remove all registered sources.

        A presenter should call this after each plan finishes.
        """
        self._sources.clear()
        self.logger.debug("Source cache reset.")

    def collect_stream_docs(
        self,
        name: str,
        indices_written: int,
    ) -> Iterator[StreamAsset]:
        """Yield ``StreamResource`` and ``StreamDatum`` documents for *name*.

        Parameters
        ----------
        name : str
            Source name.
        indices_written : int
            Number of frames to report in this call.

        Yields
        ------
        StreamAsset
            Tuples of ``("stream_resource", doc)`` or
            ``("stream_datum", doc)``.

        Raises
        ------
        KeyError
            If *name* is not registered.
        """
        if name not in self._sources:
            raise KeyError(f"Unknown source {name!r}")

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
