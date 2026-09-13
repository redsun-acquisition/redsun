from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import culsans
from ophyd_async.core import StreamResourceInfo

from ._router import FrameRouter
from ._sink import FrameSink

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any, ClassVar

    import numpy.typing as npt
    from ophyd_async.core import PathInfo, PathProvider, SignalR, StreamResourceInfo


@dataclass(frozen=True, slots=True)
class StreamSpec:
    """Specification of one channel's frame stream."""

    data_key: str
    """Channel name, such as the detector's data key."""

    shape: tuple[int, int]
    """Shape of a single frame, e.g. ``(height, width)``."""

    dtype: str
    """``numpy`` dtype of the frames, such as ``"uint8"``."""

    capacity: int | None
    """Maximum number of frames; `None` for unbounded."""

    def __post_init__(self) -> None:
        if self.capacity is not None and self.capacity <= 0:
            raise ValueError(
                f"Capacity must be None or >= 1, got {self.capacity!r} "
                f"for data_key {self.data_key!r}"
            )

    @property
    def is_unbounded(self) -> bool:
        """True if the stream has no frame limit."""
        return self.capacity is None


class OpenStore(Protocol):
    """Write path of an open multi-stream storage backend."""

    @abc.abstractmethod
    async def write(self, data_key: str, frame: npt.NDArray[Any]) -> None:
        """Write one frame for *data_key*."""

    @abc.abstractmethod
    async def release(self, data_key: str) -> None:
        """Release the stream of *data_key*."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Close the store, finalizing every resource."""


class StorageIO(Protocol):
    """Factory opening stores of one storage format."""

    mimetype: ClassVar[str]
    """Storage MIME type, e.g. ``"application/x-hdf5"``."""

    extension: ClassVar[str]
    """File extension of the format, such as ``"h5"``."""

    @abc.abstractmethod
    async def open(self, path: PathInfo, specs: Mapping[str, StreamSpec]) -> OpenStore:
        """Open a store at *path* for the given streams."""

    @abc.abstractmethod
    def uri(self, path: PathInfo, data_key: str) -> str:
        """Return the resource URI of `data_key`."""

    @abc.abstractmethod
    def resource_info(self, spec: StreamSpec) -> StreamResourceInfo:
        """Convert a `StreamSpec` to a `StreamResourceInfo` object."""


class StoreStateError(RuntimeError):
    """Raised when a storage operation is attempted in an invalid state.

    Parameters
    ----------
    verb : str
        The operation attempted.
    why : str
        Why the operation is invalid right now.
    """

    def __init__(self, verb: str, why: str) -> None:
        super().__init__(f"Cannot {verb}: {why}")
        self.verb = verb
        self.why = why


class SinkFactory(Protocol):
    """Storage API used by ``ophyd-async`` data logic and document callbacks."""

    @property
    def mimetype(self) -> str:
        """Storage MIME type, e.g. ``"application/x-hdf5"``."""

    @property
    def extension(self) -> str:
        """File extension of the format, such as ``"h5"``."""

    def register(self, spec: StreamSpec) -> None:
        """Register a stream; only allowed while the store is not open."""

    def sink(self, data_key: str) -> FrameSink:
        """Return the producer handle of `data_key`, starting its drain."""

    async def open(self) -> None:
        """Open the store, if not open yet."""

    async def close(self, *, flush: bool = True) -> None:
        """Tear the store down, flushing or dropping queued frames."""

    def uri_for(self, data_key: str) -> str:
        """Return the URI of `data_key`."""

    def resource_info_for(self, spec: StreamSpec) -> StreamResourceInfo:
        """Convert a `StreamSpec` to a `StreamResourceInfo` object."""

    def signal_for(self, data_key: str) -> SignalR[int]:
        """Return the frame counter signal of `data_key`."""


class BaseStorage(SinkFactory):
    """Manages a storage backend fed by both async and sync producers.

    Async device logic calls ``await sink(key).put(frame)``; sync document
    callbacks call ``sink(key).put_nowait(frame)``. One drain task per key,
    started by `sink`, writes frames to the backend; the last drain to end
    closes the store.

    Parameters
    ----------
    io : StorageIO
        Backend mechanics (open / uri / resource_info).
    path_provider : PathProvider
        Decides where each burst is written; asked at the first `register`.
    maxsize : int, optional
        Size of each key's frame queue.
    """

    __slots__ = (
        "_closing",
        "_drains",
        "_io",
        "_maxsize",
        "_open_lock",
        "_path",
        "_path_provider",
        "_queues",
        "_router",
        "_store",
    )

    def __init__(
        self, io: StorageIO, path_provider: PathProvider, *, maxsize: int = 100
    ) -> None:
        self._io = io
        self._path_provider = path_provider
        self._maxsize = maxsize
        self._router = FrameRouter()
        self._store: OpenStore | None = None
        self._path: PathInfo | None = None
        self._open_lock = asyncio.Lock()
        self._queues: dict[str, culsans.Queue[npt.NDArray[Any]]] = {}
        self._drains: dict[str, asyncio.Task[None]] = {}
        self._closing = False

    @property
    def mimetype(self) -> str:
        return self._io.mimetype

    @property
    def extension(self) -> str:
        return self._io.extension

    @property
    def path_provider(self) -> PathProvider:
        """The provider asked for burst paths at the first `register`."""
        return self._path_provider

    def register(self, spec: StreamSpec) -> None:
        """Register a stream.

        Raises
        ------
        StoreStateError
            If the store is open, opening or closing. `open()`, the sweep for
            orphans at close, and `_retire`'s closing section hold `_open_lock`
            throughout, so checking the lock with `_store` rules out a register
            during an open. `close()` also sets `_closing` for its whole body,
            including while suspended in the drain `gather` without `_store`
            or the lock, which rules out a register during a close.
        KeyError
            If `spec.data_key` is already registered.
        """
        if self._store is not None or self._open_lock.locked() or self._closing:
            raise StoreStateError("register", "store is open, opening, or closing")
        if len(self._router.spec) == 0:
            # first stream of the burst: allocate the path (no backend I/O)
            self._path = self._path_provider()
        self._router.add(spec)

    def sink(self, data_key: str) -> FrameSink:
        """Create the producer handle for `data_key` and spawn its drain.

        Call it on the event loop thread, where every producer runs (device
        prepare or a document callback).

        Raises
        ------
        KeyError
            If `data_key` is not registered.
        StoreStateError
            If `data_key` already has a live sink, or the storage is closing,
            since a drain started during `close()` is never awaited by its
            `gather`.
        """
        if self._closing:
            raise StoreStateError("sink", "storage is closing")
        spec = self._router.spec.get(data_key)
        if spec is None:
            raise KeyError(f"Data key {data_key!r} is not registered.")
        if data_key in self._drains:
            raise StoreStateError("sink", f"sink for {data_key!r} is already open")
        queue: culsans.Queue[npt.NDArray[Any]] = culsans.Queue(maxsize=self._maxsize)
        self._queues[data_key] = queue
        self._drains[data_key] = asyncio.get_running_loop().create_task(
            self._drain(data_key, queue, spec.capacity)
        )
        return FrameSink(queue)

    async def open(self) -> None:
        """Open the store, if not open yet.

        The first caller opens; concurrent callers wait on the lock for the
        same open. Called eagerly by device data logic when preparing, and
        lazily by each drain before its first write.

        Raises
        ------
        StoreStateError
            If no stream is registered.
        """
        async with self._open_lock:
            if self._store is not None:
                return
            if self._path is None:
                raise StoreStateError("open", "no streams registered")
            Path(self._path.directory_path).mkdir(parents=True, exist_ok=True)
            self._store = await self._io.open(self._path, dict(self._router.spec))

    async def close(self, *, flush: bool = True) -> None:
        """Tear down the current burst.

        Parameters
        ----------
        flush : bool, optional
            Write queued frames before closing; if False they are dropped, to
            abort.

        Notes
        -----
        A failed drain write does not raise at the producer: `gather` runs
        with ``return_exceptions=True``, so a drain failing mid-burst is only
        reported here. `close()` is where a burst's errors surface.
        """
        self._closing = True
        try:
            for queue in list(self._queues.values()):
                if not queue.is_shutdown:
                    queue.shutdown(immediate=not flush)
            drains = list(self._drains.values())
            results = await asyncio.gather(*drains, return_exceptions=True)
            # registered keys that never got a sink have no drain to retire them
            for key in list(self._router.spec.keys()):
                self._router.delete(key)
            # a store opened via open() with no live drains has nobody to close
            # it - every drain retired without ever seeing this store
            sweep_exc: BaseException | None = None
            try:
                if self._store is not None:
                    async with self._open_lock:
                        store = self._store
                        if store is not None:
                            self._store = None
                            try:
                                await store.close()
                            except asyncio.CancelledError:
                                raise
                            except BaseException as exc:  # noqa: BLE001 - held back so drain errors surface first
                                sweep_exc = exc
            finally:
                # by this point self._store is always None: either no store
                # ever opened, a drain's _retire already closed it, or the
                # sweep just did
                self._path = None
            # a cancelled drain re-raises as cancellation, not as a grouped
            # or bare exception
            cancelled = next(
                (r for r in results if isinstance(r, asyncio.CancelledError)), None
            )
            if cancelled is not None:
                raise cancelled
            # drain errors take priority: a write failure is the actionable
            # cause, the sweep's close failure is usually its downstream symptom
            exceptions = [r for r in results if isinstance(r, Exception)]
            if len(exceptions) > 1:
                raise ExceptionGroup("storage drain failures", exceptions)
            if exceptions:
                raise exceptions[0]
            if sweep_exc is not None:
                raise sweep_exc
        finally:
            self._closing = False

    def uri_for(self, data_key: str) -> str:
        if self._path is None:
            raise StoreStateError("compute URI", "no streams registered")
        return self._io.uri(self._path, data_key)

    def resource_info_for(self, spec: StreamSpec) -> StreamResourceInfo:
        return self._io.resource_info(spec)

    def signal_for(self, data_key: str) -> SignalR[int]:
        signal = self._router.signals.get(data_key)
        if signal is None:
            raise KeyError(f"Data key {data_key!r} is not registered.")
        return signal

    async def _drain(
        self,
        data_key: str,
        queue: culsans.Queue[npt.NDArray[Any]],
        capacity: int | None,
    ) -> None:
        """Consume one key's frames; the key's teardown happens here."""
        written = 0
        try:
            while capacity is None or written < capacity:
                try:
                    frame = await queue.async_get()
                except culsans.QueueShutDown:
                    break
                await self.open()  # lazy ensure-open; idempotent
                store = self._store
                assert store is not None  # set by open()
                await store.write(data_key, frame)
                queue.task_done()
                self._router.mark_written(data_key)
                written += 1
        finally:
            # shut producers out whether we exit by capacity, close(), or error
            if not queue.is_shutdown:
                queue.shutdown()
            await self._retire(data_key)

    async def _retire(self, data_key: str) -> None:
        """End one stream; the last drain to end closes the store.

        `self._drains.pop` runs last, in the outer `finally`. While this
        coroutine runs, `store.release()` included, the key must stay in
        `self._drains`, so a concurrent `close()` still sees this drain in its
        snapshot and awaits it through `gather` instead of closing the backend
        during the release.
        """
        try:
            self._queues.pop(data_key, None)
            self._router.delete(data_key)
            store = self._store
            if store is not None:
                try:
                    await store.release(data_key)
                finally:
                    if not self._router.spec:
                        async with self._open_lock:
                            # a concurrently retiring drain may have closed
                            # already - only the drain that still sees the
                            # store closes it
                            if self._store is not None:
                                self._store = None
                                try:
                                    await store.close()
                                finally:
                                    self._path = None
            elif not self._router.spec:
                # burst died before any frame flowed: retire the burst
                # identity so the next burst gets a fresh path
                self._path = None
        finally:
            self._drains.pop(data_key, None)
