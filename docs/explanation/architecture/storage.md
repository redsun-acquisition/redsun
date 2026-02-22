# Storage

!!! note "Design inspiration"
    The storage architecture described here is heavily inspired by
    [ophyd-async](https://github.com/bluesky/ophyd-async), developed by the
    Bluesky collaboration. The patterns — shared writer, path providers,
    `FrameSink`, `StorageProxy` protocol — were adapted to fit the
    redsun container model.

The `redsun.storage` subpackage provides the infrastructure for writing
detector frames to a persistent store. The design follows a small set of
principles:

- **One shared writer per session** — all devices write to the same store; each device owns its own array key within it.
- **Storage is opt-in per device** — devices that need storage declare a [`StorageDescriptor`][redsun.storage.StorageDescriptor] field; the base [`Device`][redsun.device.Device] class carries no storage attribute.
- **The container injects the writer** — devices never construct or look up a writer themselves; the application container builds one writer and injects it into every opted-in device at session start.
- **Backend classes are internal** — only the abstract [`Writer`][redsun.storage.Writer] and the [`StorageProxy`][redsun.storage.StorageProxy] protocol are public; concrete backends (e.g. `ZarrWriter`) are selected and instantiated by the container from the session configuration.
- **Backend dependencies are optional extras** — `acquire-zarr` is not a core dependency of redsun. Install `redsun[zarr]` to enable the Zarr backend.

---

## Opting in to storage

A device signals that it needs storage by declaring a class-level [`StorageDescriptor`][redsun.storage.StorageDescriptor]:

```python
import numpy as np
from redsun.device import Device
from redsun.storage import StorageDescriptor


class MyDetector(Device):
    storage = StorageDescriptor()

    def __init__(self, name: str, /) -> None:
        super().__init__(name)

    def prepare(self, capacity: int) -> None:
        if self.storage is None:
            raise RuntimeError("No storage backend configured for this session.")
        self.storage.update_source(
            self.name,
            dtype=np.dtype("uint16"),
            shape=(512, 512),
        )
        self._sink = self.storage.prepare(self.name, capacity=capacity)
```

The descriptor initialises to `None`; the container sets it to the shared writer
before any acquisition begins. Device code checks `self.storage is None` to handle
sessions that have no storage configured.

---

## Acquisition lifecycle

Once the writer has been injected, a device interacts with storage through a fixed
call sequence:

```python
# 1. Register the data source (dtype, shape, optional backend-specific metadata)
self.storage.update_source(self.name, dtype=np.dtype("uint16"), shape=(512, 512))

# 2. Prepare for one acquisition; returns a FrameSink bound to this device
sink = self.storage.prepare(self.name, capacity=100)

# 3. Open the backend (called once, shared across all devices)
self.storage.kickoff()

# 4. Push frames — thread-safe, multiple sinks may write concurrently
sink.write(frame)

# 5. Signal completion for this device
sink.close()
```

[`FrameSink.close`][redsun.storage.FrameSink.close] delegates to
[`Writer.complete`][redsun.storage.Writer.complete]. The backend is finalised
automatically once every active sink has been closed.

---

## Path providers

The writer resolves store paths through a composable
[`PathProvider`][redsun.storage.PathProvider]. A `PathProvider` is a callable
that accepts a device name and returns a [`PathInfo`][redsun.storage.PathInfo]
describing where and how to write that device's data.

`redsun.storage` ships three [`FilenameProvider`][redsun.storage.FilenameProvider]
strategies that can be composed with
[`StaticPathProvider`][redsun.storage.StaticPathProvider]:

=== "Static filename"

    ```python
    from redsun.storage import StaticFilenameProvider, StaticPathProvider

    # Every acquisition writes to the same filename
    path_provider = StaticPathProvider(
        StaticFilenameProvider("scan001"),
        base_uri="file:///data",
    )
    # Produces a store at /data/scan001  (array key = device name)
    ```

=== "UUID filename"

    ```python
    from redsun.storage import UUIDFilenameProvider, StaticPathProvider

    # Each acquisition gets a unique UUID filename
    path_provider = StaticPathProvider(
        UUIDFilenameProvider(),
        base_uri="file:///data",
    )
    # Produces a store at /data/3f2504e0-...  (array key = device name)
    ```

=== "Auto-increment filename"

    ```python
    from redsun.storage import AutoIncrementFilenameProvider, StaticPathProvider

    # Filenames increment: scan_00000, scan_00001, ...
    path_provider = StaticPathProvider(
        AutoIncrementFilenameProvider(base="scan", max_digits=5),
        base_uri="file:///data",
    )
    ```


---

## The StorageProxy protocol

Device code never holds a reference to a concrete backend class. It interacts
only through the [`StorageProxy`][redsun.storage.StorageProxy] protocol:

```python
from redsun.storage import StorageProxy

class StorageProxy(Protocol):
    def update_source(self, name, dtype, shape, extra=None) -> None: ...
    def prepare(self, name, capacity=0) -> FrameSink: ...
    def kickoff(self) -> None: ...
    def complete(self, name) -> None: ...
    def get_indices_written(self, name=None) -> int: ...
    def collect_stream_docs(self, name, indices_written) -> Iterator[StreamAsset]: ...
```

[`Writer`][redsun.storage.Writer] satisfies this protocol structurally, so device
code remains independent of the concrete backend.

!!! tip
    When testing devices in isolation, pass a `MagicMock(spec=StorageProxy)` as
    the injected writer — no real backend is needed and all interactions are
    captured for assertion.

    ```python
    from unittest.mock import MagicMock
    from redsun.storage import StorageProxy

    device = MyDetector("camera")
    device.storage = MagicMock(spec=StorageProxy)

    device.prepare(capacity=10)
    device.storage.update_source.assert_called_once()
    ```

---

## Implementing a custom backend

To add a new storage backend, subclass [`Writer`][redsun.storage.Writer] and
implement the four abstract members:

```python
from redsun.storage import Writer, FrameSink
import numpy.typing as npt


class MyWriter(Writer):

    @property
    def mimetype(self) -> str:
        return "application/x-myformat"

    def prepare(self, name: str, capacity: int = 0) -> FrameSink:
        # backend-specific setup for this source ...
        return super().prepare(name, capacity)  # (1)

    def kickoff(self) -> None:
        if self.is_open:
            return
        # open your backend here ...
        super().kickoff()  # (2)

    def _write_frame(self, name: str, frame: npt.NDArray) -> None:
        # write one frame to the backend under the key for `name`
        ...

    def _finalize(self) -> None:
        # close the backend; called automatically when all sinks are done
        ...
```

1. `super().prepare()` resets per-source counters and returns the bound [`FrameSink`][redsun.storage.FrameSink] — always call it.
2. `super().kickoff()` sets [`is_open`][redsun.storage.Writer.is_open] — always call it.

!!! warning
    `_write_frame` is called by [`FrameSink.write`][redsun.storage.FrameSink.write]
    **under the writer lock**. Do not acquire the lock again inside `_write_frame`
    or call any method that does.

## See also

- [`redsun.storage` API reference](../../reference/api/storage.md)
- [Devices](devices.md)
