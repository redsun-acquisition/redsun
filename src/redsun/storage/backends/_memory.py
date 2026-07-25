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
    """In-memory storage backend.

    For testing and debugging.
    """

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
        """Compute a synthetic per-burst URI, disambiguated by fragment."""
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
    """In-memory open storage.

    Keeps every written frame in a per-key list and records every call
    it receives in an ordered log, so tests can assert both *what* was
    stored and *in which order* the orchestrator drove the store.

    Contents survive `close`: tests read `arrays` after the burst ends.

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
        """Append a copy of the frame to the list for `data_key` and record the call."""
        self.calls.append(("write", data_key))
        self.arrays[data_key].append(np.copy(frame))

    async def release(self, data_key: str) -> None:
        """Record the release call for `data_key`."""
        self.calls.append(("release", data_key))

    async def close(self) -> None:
        """Record the close call."""
        self.calls.append(("close", ""))
