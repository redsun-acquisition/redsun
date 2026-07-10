from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ophyd_async.core import StreamResourceInfo

from ._fsm import InvalidStoreState, StorageStateMachine
from ._router import FrameRouter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping
    from typing import Any, ClassVar, TypeAlias

    import numpy.typing as npt
    from ophyd_async.core import PathInfo, PathProvider, SignalR, StreamResourceInfo

    FrameGenerator: TypeAlias = AsyncGenerator[None, npt.NDArray[Any]]


@dataclass(frozen=True, slots=True)
class StreamSpec:
    """Specification of a frame stream for a data sink channel."""

    data_key: str
    """Channel identity, e.g. the detector's datakey name."""

    shape: tuple[int, int]
    """Shape of a single frame, e.g. ``(height, width)``."""

    dtype: str
    """NumPy dtype of the frames (e.g. ``"uint8"``)."""

    capacity: int | None
    """Maximum number of frames. `None` means unbounded."""

    def __post_init__(self) -> None:
        if self.capacity is not None and self.capacity <= 0:
            raise ValueError(
                f"Capacity must be None or >= 1, got {self.capacity!r} "
                f"for data_key {self.data_key!r}"
            )

    @property
    def is_unbounded(self) -> bool:
        """True if the stream grows indefinitely."""
        return self.capacity is None


class OpenStore(Protocol):
    """Hot write path of a multi-stream storage backend."""

    async def write(self, data_key: str, frame: npt.NDArray[Any]) -> None:
        """Write a single frame to the storage backend for the given data key."""

    async def release(self, data_key: str) -> None:
        """Release the stream for the given data key."""

    async def close(self) -> None:
        """Close the storage backend, finalizing all resources."""


class StorageIO(Protocol):
    """Unopened store factory. Implements the API for creating a new storage backend instance."""

    mimetype: ClassVar[str]
    """Storage MIME type, e.g. ``"application/x-hdf5"``."""

    extension: ClassVar[str]
    """File extension for the storage backend, e.g. ``"h5"``."""

    async def open(self, path: PathInfo, specs: Mapping[str, StreamSpec]) -> OpenStore:
        """Open a new storage backend instance at the given path with the given stream specifications."""

    def uri(self, path: PathInfo, data_key: str) -> str:
        """Compute the resource URI for `data_key`."""

    def resource_info(self, spec: StreamSpec) -> StreamResourceInfo:
        """Convert a `StreamSpec` to a `StreamResourceInfo` object."""


class SinkFactory(Protocol):
    """Consumer API for ophyd-async data logics."""

    @property
    def mimetype(self) -> str:
        """Storage MIME type, e.g. ``"application/x-hdf5"``."""

    @property
    def extension(self) -> str:
        """File extension for the storage backend, e.g. ``"h5"``."""

    async def register(self, spec: StreamSpec) -> None:
        """Register a new stream with the backend."""

    async def __call__(self, data_key: str) -> FrameGenerator:
        """Return an async generator that pushes frames to the backend for the given `data_key`."""

    def uri_for(self, data_key: str) -> str:
        """Return the URI for the given `data_key`."""

    def resource_info_for(self, spec: StreamSpec) -> StreamResourceInfo:
        """Convert a `StreamSpec` to a `StreamResourceInfo` object."""

    def signal_for(self, data_key: str) -> SignalR[int]:
        """Return the frame counter signal for the given `data_key`."""


class BaseStorage(SinkFactory):
    """Manages the lifecycle of a storage backend for consuming data logics to use."""

    __slots__ = (
        "_io",
        "_path_provider",
        "_router",
        "_fsm",
        "_store",
        "_path",
        "_sinks",
    )

    @property
    def mimetype(self) -> str:
        return self._io.mimetype

    @property
    def extension(self) -> str:
        return self._io.extension

    def __init__(self, io: StorageIO, path_provider: PathProvider) -> None:
        self._io = io
        self._path_provider = path_provider
        self._store: OpenStore | None = None
        self._router = FrameRouter()
        self._fsm = StorageStateMachine()
        self._path: PathInfo | None = None
        self._sinks: dict[str, FrameGenerator] = {}

    async def register(self, spec: StreamSpec) -> None:
        """Register a new stream with the backend."""
        await self._fsm.ensure_registrable()
        if len(self._router.spec) == 0:
            # if the first stream is being registered,
            # compute the storage path and store it
            self._path = self._path_provider()
        self._router.add(spec)

    async def __call__(self, data_key: str) -> FrameGenerator:
        """Mint the frame sink for the given data key."""
        spec = self._router.spec.get(data_key)
        if spec is None:
            raise KeyError(f"Data key {data_key!r} is not registered.")
        if data_key in self._sinks.keys():
            raise RuntimeError(f"Sink for data key {data_key!r} is already open.")
        gen = self._pusher(data_key, spec.capacity)
        await anext(gen)  # prime the generator
        self._sinks[data_key] = gen
        return gen

    def uri_for(self, data_key: str) -> str:
        if self._path is None:
            raise InvalidStoreState(self._fsm.state, "compute URI for data key")
        return self._io.uri(self._path, data_key)

    def resource_info_for(self, spec: StreamSpec) -> StreamResourceInfo:
        return self._io.resource_info(spec)

    def signal_for(self, data_key: str) -> SignalR[int]:
        signal = self._router.signals.get(data_key)
        if signal is None:
            raise KeyError(f"Data key {data_key!r} is not registered.")
        return signal

    async def reset(self) -> None:
        """Force teardown of the backend in the current burst."""
        for gen in list(self._sinks.values()):
            await gen.aclose()
        for key in list(self._router.spec.keys()):
            await self._release(key)

    async def _pusher(self, data_key: str, capacity: int | None) -> FrameGenerator:
        """Async generator that pushes frames to the backend for the given `data_key`."""
        try:
            frame = yield
            await self._open_and_write(data_key, frame)
            self._router.mark_written(data_key)

            assert self._store is not None  # set by _open_and_write
            if capacity is None:
                while True:
                    frame = yield
                    await self._store.write(data_key, frame)
                    self._router.mark_written(data_key)
            else:
                # we already wrote the first frame,
                # so we only need to write capacity - 1 more frames
                for _ in range(capacity - 1):
                    frame = yield
                    await self._store.write(data_key, frame)
                    self._router.mark_written(data_key)
        finally:
            self._sinks.pop(data_key, None)
            await self._release(data_key)

    async def _open_and_write(self, data_key: str, frame: npt.NDArray[Any]) -> None:
        """Seal/open handshake plus the burst's first write for this key."""
        if self._fsm.try_seal():
            # a sink implies a registration, so
            # this assert is only for type-narrowing
            assert self._path is not None
            try:
                # wrap the PurePath in a Path object to use mkdir()
                Path(self._path.directory_path).mkdir(parents=True, exist_ok=True)
                self._store = await self._io.open(self._path, dict(self._router.spec))
            except BaseException as exc:
                self._fsm.open_failed(exc)
                raise
            self._fsm.open_succeeded()
        else:
            await self._fsm.await_open()
        store = self._store
        assert store is not None
        await store.write(data_key, frame)

    async def _release(self, data_key: str) -> None:
        """Retire one stream; the last one out closes the store."""
        self._router.pop(data_key)
        if self._store is not None:
            try:
                await self._store.release(data_key)
            finally:
                if not self._router.spec:
                    self._fsm.begin_close()
                    try:
                        await self._store.close()
                    finally:
                        self._store = None
                        self._path = None
                        self._fsm.close_finished()
        elif not self._router.spec:
            # burst died before any frame flowed: no store, but the
            # burst identity must still be retired so the next burst
            # mints a fresh number.
            self._path = None
