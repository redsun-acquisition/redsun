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
    from typing import Any

    import numpy as np
    import numpy.typing as npt
    from bluesky.protocols import StreamAsset
    from event_model.documents import StreamDatum, StreamResource


@dataclass
class SourceInfo:
    """Runtime acquisition state for a registered data source.

    Tracks per-source counters and identifiers used during an acquisition.
    This dataclass is internal to [`Writer`][redsun.storage.Writer].

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

    name: str
    dtype: np.dtype[np.generic]
    shape: tuple[int, ...]
    data_key: str
    capacity: int = 0
    frames_written: int = 0
    collection_counter: int = 0
    stream_resource_uid: str = field(default_factory=lambda: str(uuid.uuid4()))


class FrameSink:
    """Device-facing handle for pushing frames to a storage backend.

    Returned by [`Writer.register`][redsun.storage.Writer.register].
    Devices write frames by calling [`write`][redsun.storage.FrameSink.write];
    the sink routes each frame to the backend and updates the frame counter
    atomically.

    Calling [`close`][redsun.storage.FrameSink.close] signals that no more
    frames will arrive from this source and triggers backend finalisation
    once all sources are complete.

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
        """Push ``frame`` to the storage backend.

        Thread-safe.

        Parameters
        ----------
        frame : npt.NDArray[np.generic]
            Array data to write. dtype and shape must match those declared
            in [`Writer.register`][redsun.storage.Writer.register].
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

    Example keys:

        ("default", "application/x-zarr")  # the normal single-store case
        ("live", "application/x-zarr")     # a separate live-preview store
        ("default", "application/x-hdf5")  # a different format entirely

    URI setting is controlled by the Presenter layer
    via [`set_uri`][redsun.storage.Writer.set_uri].
    Subclasses must override ``set_uri`` to perform any backend-specific path
    translation without disturbing the registry.

    Call order per acquisition:

    1. ``set_uri(uri)`` — called by a presenter before the plan
    2. ``register(source_name, data_key, dtype, shape, capacity)`` — called
       by each device in its own ``prepare()``; returns a
       [`FrameSink`][redsun.storage.FrameSink]
    3. ``kickoff()`` — opens the backend
    4. ``sink.write(frame)`` — push frames (thread-safe)
    5. ``sink.close()`` — signals completion for this source

    Subclasses must implement:

    - [`mimetype`][redsun.storage.Writer.mimetype] — MIME type string
    - [`_on_register`][redsun.storage.Writer._on_register] — backend-specific
      setup after a source is registered (e.g. pre-declare Zarr array
      dimensions); called at the end of ``register``
    - [`kickoff`][redsun.storage.Writer.kickoff] — open the backend;
      must call ``super().kickoff()``
    - [`_write_frame`][redsun.storage.Writer._write_frame] — write one frame to the backend
    - [`_finalize`][redsun.storage.Writer._finalize] — close the backend when all sources are done

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
        The URI is *not* set here — call
        [`set_uri`][redsun.storage.Writer.set_uri] separately.

        This method is normally not called directly by devices or
        application code.  Use
        [`make_writer`][redsun.storage.make_writer] instead, which
        resolves the correct subclass from the mimetype string.

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
        # cls.mimetype is an abstract property; each concrete subclass
        # provides a fixed string (e.g. ZarrWriter.mimetype == "application/x-zarr").
        # We access it via the class directly to avoid needing an instance.
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

        Called by ``StoragePresenter`` at application shutdown.
        Devices should not call this directly.

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

        Used by [`get`][redsun.storage.Writer.get] and
        [`release`][redsun.storage.Writer.release] to build the registry
        key before any instance exists.  Must return the same value as
        the instance property [`mimetype`][redsun.storage.Writer.mimetype].

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
        """The current store URI.

        Empty string until
        [`set_uri`][redsun.storage.Writer.set_uri] has been called.
        """
        return self._uri

    @property
    def mimetype(self) -> str:
        """The MIME type string for this backend.

        Must return the same value as
        [`_class_mimetype`][redsun.storage.Writer._class_mimetype].
        """
        return self._class_mimetype()

    def set_uri(self, uri: str) -> None:
        """Update the store URI for the next acquisition.

        Called by ``StoragePresenter`` before each acquisition and
        whenever the user changes the output directory.  The writer
        must not be open when this is called.

        Subclasses should override this to perform any backend-specific
        path translation (e.g. rebuilding ``StreamSettings.store_path``
        for ``ZarrWriter``) and must call ``super().set_uri(uri)``.

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

    def prepare(
        self,
        name: str,
        data_key: str,
        dtype: np.dtype[np.generic],
        shape: tuple[int, ...],
        capacity: int = 0,
    ) -> FrameSink:
        """Register a data source and return a ready ``FrameSink``.

        Called by each device inside its own ``prepare()`` method, once
        per acquisition.  Replaces the former two-step
        ``update_source`` + ``prepare`` sequence.

        Safe to call multiple times on the same source name — counters
        are reset on each call, making it suitable for repeated
        acquisitions without recreating the writer.

        Parameters
        ----------
        name : str
            Source name, typically the device name.  Multiple devices
            may register distinct source names on the same writer.
        data_key : str
            Bluesky data key used in stream documents.
        dtype : np.dtype[np.generic]
            NumPy data type of the frames.
        shape : tuple[int, ...]
            Shape of each individual frame.
        capacity : int
            Maximum number of frames to accept.  ``0`` means unlimited.

        Returns
        -------
        FrameSink
            Bound sink ready to accept frames via ``sink.write(frame)``.

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
            data_key=data_key,
            capacity=capacity,
        )
        self.logger.debug(
            f"Registered source {name!r} — shape={shape}, capacity={capacity}"
        )
        self._on_prepare(name)
        return FrameSink(self, name)

    @abc.abstractmethod
    def _on_prepare(self, name: str) -> None:
        """Backend-specific hook called after a source is registered.

        Invoked at the end of [`register`][redsun.storage.Writer.register]
        once ``self._sources[name]`` is fully populated.  Subclasses use
        this to pre-declare backend structures — for example, ``ZarrWriter``
        builds its ``ArraySettings`` here from the source dtype and shape.

        Parameters
        ----------
        name : str
            The source name just registered.
        """
        ...

    def clear_source(self, name: str, *, raise_if_missing: bool = False) -> None:
        """Remove a registered data source.

        Parameters
        ----------
        name : str
            Source name to remove.
        raise_if_missing : bool
            If ``True``, raise ``KeyError`` when the source is absent.

        Raises
        ------
        RuntimeError
            If the writer is currently open.
        KeyError
            If *raise_if_missing* is ``True`` and the source is absent.
        """
        if self._is_open:
            raise RuntimeError("Cannot clear sources while writer is open.")
        try:
            del self._sources[name]
            self.logger.debug(f"Cleared source {name!r}")
        except KeyError as exc:
            self.logger.error(f"Source {name!r} not found.")
            if raise_if_missing:
                raise exc

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

    @abc.abstractmethod
    def kickoff(self) -> None:
        """Open the storage backend for a new acquisition.

        Subclasses must call ``super().kickoff()`` to set
        [`is_open`][redsun.storage.Writer.is_open] and to enforce the
        URI guard.  Subsequent calls while already open must be no-ops.

        Raises
        ------
        RuntimeError
            If [`uri`][redsun.storage.Writer.uri] has not been set yet.
        """
        from redsun.storage.metadata import clear_metadata, snapshot_metadata

        if not self._uri:
            clear_metadata()
            raise RuntimeError(
                f"Writer ({self._name!r}, {self.mimetype!r}) has no URI. "
                "StoragePresenter must call set_uri() before kickoff()."
            )
        if not self._is_open:
            self._metadata = snapshot_metadata()
            self._is_open = True

    def complete(self, name: str) -> None:
        """Mark acquisition complete for source *name*.

        Called automatically by [`FrameSink.close`][redsun.storage.FrameSink.close].
        When the last registered source calls ``complete``, the backend
        is finalised and ``is_open`` is reset.  The writer instance
        remains in the registry and is ready for the next acquisition.

        Parameters
        ----------
        name : str
            Source name signalling completion.
        """
        self._sources.pop(name, None)
        if not self._sources:
            self._finalize()
            self._is_open = False
            from redsun.storage.metadata import clear_metadata

            clear_metadata()
            self.logger.debug("All sources complete; backend finalised.")

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
        """Close the backend after all sources have completed."""
        ...

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
