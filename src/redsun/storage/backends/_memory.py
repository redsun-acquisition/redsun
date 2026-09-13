from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from ophyd_async.core import PathInfo, StreamResourceInfo

from redsun.storage._base import StreamSpec

from .._base import OpenStore, StorageIO

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    import numpy.typing as npt
    from ophyd_async.core import PathInfo

    from .._base import StreamSpec

__all__ = ["MemoryIO", "MemoryStore"]


class MemoryIO(StorageIO):
    """In-memory storage backend, for tests and debugging."""

    mimetype = "application/x-memory"
    extension = ""

    __slots__ = ("stores",)

    def __init__(self) -> None:
        self.stores: list[MemoryStore] = []

    async def open(self, path: PathInfo, specs: Mapping[str, StreamSpec]) -> OpenStore:
        store = MemoryStore(path, specs)
        self.stores.append(store)
        return store

    def uri(self, path: PathInfo, data_key: str) -> str:
        """Return a made-up URI per burst, with the key as fragment."""
        return f"memory://{path.directory_path.as_posix()}/{path.filename}#{data_key}"

    def resource_info(self, spec: StreamSpec) -> StreamResourceInfo:
        return StreamResourceInfo(
            data_key=spec.data_key,
            shape=spec.shape,
            chunk_shape=(1, *spec.shape),
            dtype_numpy=np.dtype(spec.dtype).str,
            parameters={},
        )


class MemoryStore(OpenStore):
    """In-memory open store.

    Keeps each key's written frames in a list and logs every call in order,
    so tests can assert *what* was stored and *in which order* the store was
    driven. Contents survive `close`, so tests read `arrays` after the burst.

    Parameters
    ----------
    path : PathInfo
        The burst's path, kept for assertions. Nothing is written to disk.
    specs : Mapping[str, StreamSpec]
        The complete spec map the store was opened with.
    """

    __slots__ = ("arrays", "calls", "path", "specs")

    def __init__(self, path: PathInfo, specs: Mapping[str, StreamSpec]) -> None:
        self.path = path
        self.specs = dict(specs)
        self.arrays: dict[str, list[np.ndarray]] = {key: [] for key in specs}
        self.calls: list[tuple[str, str]] = []

    async def write(self, data_key: str, frame: npt.NDArray[Any]) -> None:
        """Store a copy of the frame under `data_key` and log the call."""
        self.calls.append(("write", data_key))
        self.arrays[data_key].append(np.copy(frame))

    async def release(self, data_key: str) -> None:
        """Log the release of `data_key`."""
        self.calls.append(("release", data_key))

    async def close(self) -> None:
        """Log the close."""
        self.calls.append(("close", ""))
