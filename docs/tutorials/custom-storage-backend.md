# Writing a custom storage backend

`redsun` ships an in-memory backend, for tests, and an
[acquire-zarr](https://github.com/acquire-project/acquire-zarr) backend.
Another format takes two small classes. This tutorial builds a simple
raw-binary backend, writing each stream to a flat `.bin` file beside a JSON
sidecar, and drives it through [`BaseStorage`][redsun.storage.BaseStorage].

The format is kept simple on purpose; the contract is what matters.

## The contract

A backend has two parts (the
[storage redesign decision](../explanation/decisions/0002-storage-dual-context-redesign.md)
explains why):

- [`StorageIO`][redsun.storage.StorageIO], the factory before opening. It
  knows the format (`mimetype`, `extension`), how to `open` a store at a path,
  and how to describe streams to `bluesky` (`uri`, `resource_info`).
- [`OpenStore`][redsun.storage.OpenStore], the write path `open` returns. It
  writes (`write`), releases finished streams (`release`) and closes
  (`close`).

You never call `OpenStore` yourself: `BaseStorage` manages its lifecycle.
Producers, async device logic and sync document callbacks, only see a
[`FrameSink`][redsun.storage.FrameSink].

## Step 1: the open store

Create `raw_backend.py` and start with the write path:

```python
from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
from ophyd_async.core import StreamResourceInfo

from redsun.storage import OpenStore, StorageIO, StreamSpec

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path
    from typing import Any, BinaryIO

    import numpy.typing as npt
    from ophyd_async.core import PathInfo


class RawStore(OpenStore):
    """One open burst: a flat binary file per stream plus a JSON sidecar."""

    def __init__(
        self, directory: Path, filename: str, specs: Mapping[str, StreamSpec]
    ) -> None:
        self._files: dict[str, BinaryIO] = {}
        self._counts: dict[str, int] = {}
        self._sidecar = directory / f"{filename}.json"
        self._meta: dict[str, dict[str, Any]] = {}
        for key, spec in specs.items():
            path = directory / f"{filename}-{key}.bin"
            self._files[key] = path.open("wb")
            self._counts[key] = 0
            self._meta[key] = {
                "file": path.name,
                "shape": list(spec.shape),
                "dtype": spec.dtype,
            }

    async def write(self, data_key: str, frame: npt.NDArray[Any]) -> None:
        """Append one frame's bytes to the stream's file."""
        self._files[data_key].write(frame.tobytes())
        self._counts[data_key] += 1

    async def release(self, data_key: str) -> None:
        """Flush and close the finished stream, recording its frame count."""
        self._meta[data_key]["frames"] = self._counts[data_key]
        self._files.pop(data_key).close()

    async def close(self) -> None:
        """Close any stream not yet released and write the sidecar."""
        for key, file in self._files.items():
            self._meta[key]["frames"] = self._counts[key]
            file.close()
        self._files.clear()
        self._sidecar.write_text(json.dumps(self._meta, indent=2))
```

Note:

- `write` receives the `data_key` on every call: one store serves every
  stream registered for the burst.
- `release` is called once per stream when its drain ends (at capacity or
  teardown). `close` is called exactly once, by the last drain to end, and
  cleans up any stream still open.
- The methods are `async`, but this implementation blocks the event loop on
  file I/O. That is acceptable here and on fast local disks; a production
  backend should use a library that buffers on its own thread, as
  `acquire-zarr` does.

## Step 2: the IO factory

Below `RawStore`, add the factory:

```python
class RawIO(StorageIO):
    """Raw-binary backend: one flat ``.bin`` file per stream."""

    mimetype = "application/x-raw"
    extension = "bin"

    async def open(self, path: PathInfo, specs: Mapping[str, StreamSpec]) -> OpenStore:
        """Open all per-stream files for this burst."""
        return RawStore(path.directory_path, path.filename, specs)

    def uri(self, path: PathInfo, data_key: str) -> str:
        """Point at the stream's own file."""
        target = path.directory_path / f"{path.filename}-{data_key}.bin"
        return target.as_uri()

    def resource_info(self, spec: StreamSpec) -> StreamResourceInfo:
        """Describe the stream for bluesky ``StreamResource`` documents."""
        return StreamResourceInfo(
            data_key=spec.data_key,
            shape=spec.shape,
            chunk_shape=(1, *spec.shape),
            dtype_numpy=np.dtype(spec.dtype).str,
            parameters={},
        )
```

- `mimetype` identifies the backend in the
  [storage registry][redsun.storage.register_storage]; choose something unique
  and stable.
- `uri` and `resource_info` let device data logic emit `StreamResource`
  documents pointing at your files, which a reader in your analysis
  environment uses to find and interpret the data. One `.bin` file holds one
  stream, so the URI is that file. `parameters` can carry format-specific
  hints for a reader.

## Step 3: drive it

`BaseStorage` handles queueing, backpressure, lazy opening and teardown order.
Append a demo:

```python
import asyncio
from pathlib import Path

from redsun.storage import BaseStorage, SessionPathProvider


async def main() -> None:
    # paths must be absolute - PathInfo rejects relative directories
    provider = SessionPathProvider(
        base_dir=Path("raw-demo").resolve(), session="tutorial"
    )
    storage = BaseStorage(RawIO(), provider)

    # declare the burst's streams - only legal while the store is closed
    storage.register(StreamSpec("camera", shape=(64, 64), dtype="uint16", capacity=10))
    storage.register(StreamSpec("stats", shape=(1, 4), dtype="float64", capacity=10))

    camera = storage.sink("camera")  # spawns the drain task for the key
    stats = storage.sink("stats")

    rng = np.random.default_rng()
    for _ in range(10):
        await camera.put(rng.integers(0, 65535, (64, 64), dtype="uint16"))
        await stats.put(rng.random((1, 4)))

    # flush queued frames and tear the burst down
    await storage.close(flush=True)


if __name__ == "__main__":
    asyncio.run(main())
```

Run it:

```bash
python raw_backend.py
```

It writes the session layout `raw-demo/tutorial/<YYYY-MM-DD>/unknown_00000-{camera,stats}.bin`
and the `unknown_00000.json` sidecar (the plan name is `unknown` until a
presenter sets it). Reading a stream back takes one line:

```python
frames = np.fromfile(
    "raw-demo/tutorial/<date>/unknown_00000-camera.bin", dtype="uint16"
).reshape(-1, 64, 64)
```

You wrote no queues, tasks or open and close ordering. `register` allocated the
burst path, the first frame through a drain opened the store, capacity (or
`close`) shut the sinks down, and the last drain to end closed `RawStore`.

## Where to go next

- **Share it across the application**: put the instance in the process-wide
  registry with
  [`register_storage("group", storage)`][redsun.storage.register_storage], so
  device data logic and document callbacks get the same instance from
  [`get_storage`][redsun.storage.get_storage].
- **Feed it from devices and callbacks**: the
  [session storage explanation](../explanation/storage.md) covers how
  `StandardDetector` data logic and document callbacks share one store, and
  when each may write.
- **Rely on the lifecycle**: the
  [dual-context redesign ADR](../explanation/decisions/0002-storage-dual-context-redesign.md)
  guarantees `open` once per burst, `write`/`release` only between `open` and
  `close`, and `close` exactly once.
