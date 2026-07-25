from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import culsans
import numpy as np
import pytest

from redsun.storage import SessionPathProvider, StreamSpec
from redsun.storage._base import BaseStorage, OpenStore, StoreStateError
from redsun.storage.backends._memory import MemoryIO, MemoryStore

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path
    from typing import Any

    import numpy.typing as npt
    from ophyd_async.core import PathInfo


class _GatedStore(MemoryStore):
    def __init__(
        self, path: PathInfo, specs: Mapping[str, StreamSpec], gate: asyncio.Event
    ) -> None:
        super().__init__(path, specs)
        self.gate = gate

    async def write(self, data_key: str, frame: npt.NDArray[Any]) -> None:
        await self.gate.wait()
        await super().write(data_key, frame)


class GatedIO(MemoryIO):
    def __init__(self) -> None:
        super().__init__()
        self.gate = asyncio.Event()

    async def open(self, path: PathInfo, specs: Mapping[str, StreamSpec]) -> OpenStore:
        store = _GatedStore(path, specs, self.gate)
        self.stores.append(store)
        return store

    def set_gate(self) -> None:
        self.gate.set()

    def clear_gate(self) -> None:
        self.gate.clear()


def spec(data_key: str, capacity: int | None = None) -> StreamSpec:
    """Return a `StreamSpec` object with `shape=(4, 4)` and `dtype="uint16"."""
    return StreamSpec(
        data_key=data_key, shape=(4, 4), dtype="uint16", capacity=capacity
    )


def frame(fill: int = 0) -> npt.NDArray[Any]:
    """Return a 4x4 frame filled with the specified value."""
    return np.full((4, 4), fill, dtype=np.uint16)


@pytest.fixture
def provider(tmp_path: Path) -> SessionPathProvider:
    """Return a `SessionPathProvider` object with a temporary base directory."""
    return SessionPathProvider(base_dir=tmp_path, session="test_session")


@pytest.fixture
def io() -> MemoryIO:
    return MemoryIO()


@pytest.fixture
def storage(io: MemoryIO, provider: SessionPathProvider) -> BaseStorage:
    return BaseStorage(io=io, path_provider=provider)


async def test_happy_path_register_sink_write_to_capacity(
    storage: BaseStorage, io: MemoryIO
) -> None:
    """One key: register -> sink -> put x3 -> lazy open -> capacity closes."""
    storage.register(spec("det", capacity=3))
    # captured at register time: sink() spawns the drain, whose last write
    # retires the router entry, so the signal must be in hand before that
    signal = storage.signal_for("det")
    sink = storage.sink("det")
    for i in range(3):
        await sink.put(frame(i))
    # deterministic wait: the drain shuts the queue down synchronously right
    # after marking the 3rd write, before its next suspension point — no
    # scheduling assumption needed once the counter confirms the write
    while await signal.get_value() < 3:
        await asyncio.sleep(0)
    # capacity reached: producers are shut out
    with pytest.raises(culsans.QueueShutDown):
        await sink.put(frame(99))
    await storage.close()  # waits for the drain; no-op teardown if already done
    assert len(io.stores) == 1
    store = io.stores[0]
    assert [f[0, 0] for f in store.arrays["det"]] == [0, 1, 2]
    assert store.calls[-1] == ("close", "")


async def test_open_is_idempotent_and_lazy_open_happens_on_first_write(
    storage: BaseStorage, io: MemoryIO
) -> None:
    storage.register(spec("det", capacity=1))
    sink = storage.sink("det")
    assert io.stores == []  # nothing opened yet
    await storage.open()
    await storage.open()  # second call is a no-op
    assert len(io.stores) == 1
    await sink.put(frame(5))
    await storage.close()
    assert len(io.stores) == 1  # still the same store


async def test_register_while_open_raises(storage: BaseStorage, io: MemoryIO) -> None:
    storage.register(spec("det", capacity=1))
    await storage.open()
    with pytest.raises(StoreStateError):
        storage.register(spec("late", capacity=1))
    await storage.close()
    # the store opened but never got a sink/drain — close() must still
    # close it, not leak it open forever
    assert io.stores[0].calls[-1] == ("close", "")


async def test_sink_requires_registration_and_is_single_use(
    storage: BaseStorage,
) -> None:
    with pytest.raises(KeyError):
        storage.sink("ghost")
    storage.register(spec("det", capacity=1))
    storage.sink("det")
    with pytest.raises(StoreStateError):
        storage.sink("det")
    await storage.close()


async def test_counter_advances_only_on_actual_write(
    storage: BaseStorage,
) -> None:
    storage.register(spec("det", capacity=2))
    sink = storage.sink("det")
    signal = storage.signal_for("det")
    assert await signal.get_value() == 0
    await sink.put(frame())
    await sink.put(frame())
    await storage.close()
    assert await signal.get_value() == 2


async def test_open_failure_propagates_and_is_retryable(
    provider: SessionPathProvider,
) -> None:
    class FailingIO(MemoryIO):
        def __init__(self) -> None:
            super().__init__()
            self.fail = True

        async def open(
            self, path: PathInfo, specs: Mapping[str, StreamSpec]
        ) -> OpenStore:
            if self.fail:
                raise OSError("disk on fire")
            return await super().open(path, specs)

    failing_io = FailingIO()
    storage = BaseStorage(io=failing_io, path_provider=provider)
    storage.register(spec("det", capacity=1))
    with pytest.raises(OSError, match="disk on fire"):
        await storage.open()
    failing_io.fail = False
    await storage.open()  # lock released — retry succeeds
    assert len(failing_io.stores) == 1
    await storage.close()


async def test_register_while_opening_raises(provider: SessionPathProvider) -> None:
    class _SlowOpenIO(MemoryIO):
        def __init__(self) -> None:
            super().__init__()
            self.gate = asyncio.Event()

        async def open(
            self, path: PathInfo, specs: Mapping[str, StreamSpec]
        ) -> OpenStore:
            await self.gate.wait()
            return await super().open(path, specs)

    io = _SlowOpenIO()
    storage = BaseStorage(io=io, path_provider=provider)
    storage.register(spec("det", capacity=1))
    open_task = asyncio.create_task(storage.open())
    while not storage._open_lock.locked():
        await asyncio.sleep(0)
    with pytest.raises(StoreStateError):
        storage.register(spec("late", capacity=1))
    io.gate.set()
    await open_task
    await storage.close()


async def test_register_while_closing_raises(provider: SessionPathProvider) -> None:
    class _SlowCloseStore(MemoryStore):
        def __init__(
            self,
            path: PathInfo,
            specs: Mapping[str, StreamSpec],
            gate: asyncio.Event,
        ) -> None:
            super().__init__(path, specs)
            self._gate = gate

        async def close(self) -> None:
            await self._gate.wait()
            await super().close()

    class _SlowCloseIO(MemoryIO):
        def __init__(self) -> None:
            super().__init__()
            self.gate = asyncio.Event()

        async def open(
            self, path: PathInfo, specs: Mapping[str, StreamSpec]
        ) -> OpenStore:
            store = _SlowCloseStore(path, specs, self.gate)
            self.stores.append(store)
            return store

    io = _SlowCloseIO()
    storage = BaseStorage(io=io, path_provider=provider)
    storage.register(spec("det", capacity=1))
    sink = storage.sink("det")
    await sink.put(frame())
    close_task = asyncio.create_task(storage.close())
    while not storage._open_lock.locked():
        await asyncio.sleep(0)
    with pytest.raises(StoreStateError):
        storage.register(spec("late", capacity=1))
    io.gate.set()
    await close_task


async def test_sink_close_flushes_queued_frames(
    storage: BaseStorage, io: MemoryIO
) -> None:
    """Unbounded stream: sink.close() writes what is queued, then closes."""
    storage.register(spec("det", capacity=None))
    sink = storage.sink("det")
    await sink.put(frame(1))
    await sink.put(frame(2))
    sink.close()
    await storage.close()  # await the drain deterministically
    assert [f[0, 0] for f in io.stores[0].arrays["det"]] == [1, 2]


async def test_close_without_flush_drops_queued_frames(
    provider: SessionPathProvider,
) -> None:
    gated = GatedIO()
    storage = BaseStorage(io=gated, path_provider=provider)
    storage.register(spec("det", capacity=None))
    sink = storage.sink("det")
    await sink.put(frame(1))  # drain blocks inside gated write
    await asyncio.sleep(0)  # let the drain pick the frame up and open
    await sink.put(frame(2))  # stays queued
    gated.set_gate()
    await storage.close(flush=False)
    # frame 1 was in-flight and completes; frame 2 was dropped
    assert [f[0, 0] for f in gated.stores[0].arrays["det"]] == [1]


async def test_burst_that_never_flowed_leaves_no_store_and_resets_path(
    storage: BaseStorage, io: MemoryIO, provider: SessionPathProvider
) -> None:
    storage.register(spec("det", capacity=3))
    storage.sink("det")
    await storage.close()  # no frame ever flowed
    assert io.stores == []
    # a fresh burst re-registers the same key under a new path
    storage.register(spec("det", capacity=1))
    sink = storage.sink("det")
    await sink.put(frame(9))
    await storage.close()
    assert len(io.stores) == 1


async def test_concurrent_keys_single_open_single_close(
    storage: BaseStorage, io: MemoryIO
) -> None:
    """N keys racing: exactly one backend open, exactly one close."""
    keys = [f"det{i}" for i in range(4)]
    for key in keys:
        storage.register(spec(key, capacity=2))
    sinks = {key: storage.sink(key) for key in keys}

    async def produce(key: str) -> None:
        for i in range(2):
            await sinks[key].put(frame(i))

    await asyncio.gather(*(produce(key) for key in keys))
    await storage.close()
    assert len(io.stores) == 1
    store = io.stores[0]
    for key in keys:
        assert len(store.arrays[key]) == 2
    assert sum(1 for call in store.calls if call == ("close", "")) == 1


async def test_register_during_close_gather_window_raises(
    provider: SessionPathProvider,
) -> None:
    """Registering while `close()` is suspended in its `gather` must be rejected.

    Regression test for the register-during-close race: without the
    `_closing` guard, the last drain's `_retire` can null `_store` and close
    the backend *before* `close()` resumes from `await asyncio.gather(...)`.
    In that window `register()`'s old guard (`_store is None` and the lock
    free) passed, so a concurrently scheduled `register()` (e.g. a device
    `prepare` for the next burst) would succeed — only for `close()`'s
    router sweep and `finally: self._path = None` to silently destroy it
    once it resumed. The `_closing` flag, set for the whole body of
    `close()`, closes that window.
    """

    class _SlowWriteStore(MemoryStore):
        def __init__(
            self, path: PathInfo, specs: Mapping[str, StreamSpec], gate: asyncio.Event
        ) -> None:
            super().__init__(path, specs)
            self._gate = gate

        async def write(self, data_key: str, frame: npt.NDArray[Any]) -> None:
            await self._gate.wait()
            await super().write(data_key, frame)

    class _SlowWriteIO(MemoryIO):
        def __init__(self) -> None:
            super().__init__()
            self.gate = asyncio.Event()

        async def open(
            self, path: PathInfo, specs: Mapping[str, StreamSpec]
        ) -> OpenStore:
            store = _SlowWriteStore(path, specs, self.gate)
            self.stores.append(store)
            return store

    io = _SlowWriteIO()
    storage = BaseStorage(io=io, path_provider=provider)

    storage.register(spec("a"))
    sink_a = storage.sink("a")
    drain_task = storage._drains["a"]
    await sink_a.put(frame(1))
    # let the drain pick the frame up and park inside the gated write
    while not io.stores:
        await asyncio.sleep(0)

    close_task = asyncio.create_task(storage.close())
    await asyncio.sleep(0)  # close() shuts queues and parks in gather

    # register burst B the instant drain A completes: this done-callback is
    # scheduled after gather's own bookkeeping callback but before close()'s
    # own resumption -- exactly where an independently scheduled task step
    # (e.g. a device prepare) can land in a real app
    outcome: dict[str, StoreStateError | None] = {}

    def _register_b(_task: asyncio.Task[None]) -> None:
        try:
            storage.register(spec("b"))
        except StoreStateError as exc:
            outcome["error"] = exc
        else:
            outcome["error"] = None

    drain_task.add_done_callback(_register_b)

    # release the gate: drain A finishes the write, retires, and (last
    # drain out) closes the store, before close() resumes
    io.gate.set()
    while not drain_task.done():
        await asyncio.sleep(0)

    await close_task
    assert "error" in outcome, "register callback never ran inside the window"
    assert isinstance(outcome["error"], StoreStateError)
    # burst B must never have been registered
    assert "b" not in storage._router.spec


async def test_close_awaits_inflight_release_before_backend_close(
    provider: SessionPathProvider,
) -> None:
    """`close()` must wait for an in-flight `release()` before closing the backend.

    Regression test: `_retire` used to pop its own entry out of
    `self._drains` before awaiting `store.release()`. A concurrent `close()`
    snapshotting `self._drains` in that window would miss the retiring
    drain, skip waiting for it in `gather`, and race ahead to close the
    backend while `release()` was still in flight. Moving the
    `self._drains.pop` to the end of `_retire` keeps the drain visible to
    `close()` for its whole lifetime, so `close()`'s `gather` now naturally
    awaits the drain (release, then close) before its own sweep runs.
    """

    class _GatedReleaseStore(MemoryStore):
        def __init__(
            self, path: PathInfo, specs: Mapping[str, StreamSpec], gate: asyncio.Event
        ) -> None:
            super().__init__(path, specs)
            self._gate = gate

        async def release(self, data_key: str) -> None:
            await self._gate.wait()
            await super().release(data_key)

    class _GatedReleaseIO(MemoryIO):
        def __init__(self) -> None:
            super().__init__()
            self.gate = asyncio.Event()

        async def open(
            self, path: PathInfo, specs: Mapping[str, StreamSpec]
        ) -> OpenStore:
            store = _GatedReleaseStore(path, specs, self.gate)
            self.stores.append(store)
            return store

    io = _GatedReleaseIO()
    storage = BaseStorage(io=io, path_provider=provider)
    storage.register(spec("det", capacity=1))
    sink = storage.sink("det")
    await sink.put(frame())
    # wait for the write to land: capacity=1 means the drain then exits its
    # loop and calls _retire, parking inside the gated release
    while not io.stores or ("write", "det") not in io.stores[0].calls:
        await asyncio.sleep(0)

    close_task = asyncio.create_task(storage.close())
    await asyncio.sleep(0)  # close() must be waiting on the drain, not racing it

    io.gate.set()
    await close_task

    calls = io.stores[0].calls
    assert calls.index(("release", "det")) < calls.index(("close", ""))


async def test_drain_write_failure_surfaces_at_close(
    provider: SessionPathProvider,
) -> None:
    """A drain write failure is swallowed by `gather` and only surfaces at `close()`.

    The producer's own next `put` just sees `QueueShutDown` -- indistinguishable
    from ordinary capacity shutdown, by design. `close()` is the error
    observation point: it is what drives the failed drain to completion (via
    its `gather`) and re-raises what the drain raised. `release()` is gated
    here purely to hold the drain open long enough for the test to observe
    both the shutdown queue and the still-pending drain deterministically.
    """

    class _FailAfterStore(MemoryStore):
        def __init__(
            self,
            path: PathInfo,
            specs: Mapping[str, StreamSpec],
            fail_after: int,
            gate: asyncio.Event,
        ) -> None:
            super().__init__(path, specs)
            self._fail_after = fail_after
            self._writes = 0
            self._gate = gate

        async def write(self, data_key: str, frame: npt.NDArray[Any]) -> None:
            self._writes += 1
            if self._writes > self._fail_after:
                raise RuntimeError("disk fault")
            await super().write(data_key, frame)

        async def release(self, data_key: str) -> None:
            await self._gate.wait()
            await super().release(data_key)

    class _FailAfterIO(MemoryIO):
        def __init__(self, fail_after: int) -> None:
            super().__init__()
            self._fail_after = fail_after
            self.gate = asyncio.Event()

        async def open(
            self, path: PathInfo, specs: Mapping[str, StreamSpec]
        ) -> OpenStore:
            store = _FailAfterStore(path, specs, self._fail_after, self.gate)
            self.stores.append(store)
            return store

    io = _FailAfterIO(fail_after=2)
    storage = BaseStorage(io=io, path_provider=provider)
    storage.register(spec("det", capacity=None))
    sink = storage.sink("det")
    drain_task = storage._drains["det"]
    await sink.put(frame(1))
    await sink.put(frame(2))
    await sink.put(frame(3))  # the drain's write for this frame raises

    # the drain shuts its queue down synchronously on the way out, then
    # parks in the gated release: wait for that window deterministically
    while not io.stores or io.stores[0]._writes < 3:  # type: ignore[attr-defined]
        await asyncio.sleep(0)
    assert not drain_task.done()

    # the queue is already shut down: a producer sees this exactly like an
    # ordinary capacity/close shutdown -- indistinguishable, by design
    with pytest.raises(culsans.QueueShutDown):
        await sink.put(frame(4))

    close_task = asyncio.create_task(storage.close())
    await asyncio.sleep(0)  # close() picks the still-live drain up in gather

    io.gate.set()
    with pytest.raises(RuntimeError, match="disk fault"):
        await close_task

    assert [f[0, 0] for f in io.stores[0].arrays["det"]] == [1, 2]


async def test_registered_key_without_sink_is_cleaned_by_close(
    storage: BaseStorage, io: MemoryIO
) -> None:
    storage.register(spec("used", capacity=1))
    storage.register(spec("orphan", capacity=1))
    sink = storage.sink("used")
    await sink.put(frame())
    await storage.close()
    # next burst can re-register both keys
    storage.register(spec("used", capacity=1))
    storage.register(spec("orphan", capacity=1))
    await storage.close()


@pytest.mark.parametrize("capacity", [0, -1])
def test_stream_spec_rejects_nonpositive_capacity(capacity: int) -> None:
    with pytest.raises(ValueError, match="Capacity must be None or >= 1"):
        spec("det", capacity=capacity)


def test_stream_spec_unbounded_flag() -> None:
    assert spec("det", capacity=None).is_unbounded
    assert not spec("det", capacity=1).is_unbounded


async def test_lookup_and_state_errors(storage: BaseStorage, io: MemoryIO) -> None:
    """Misuse before any registration fails loudly, never silently."""
    assert storage.extension == io.extension
    with pytest.raises(StoreStateError):
        storage.uri_for("det")
    with pytest.raises(KeyError):
        storage.signal_for("det")
    with pytest.raises(StoreStateError):
        await storage.open()


async def test_sink_while_closing_raises(provider: SessionPathProvider) -> None:
    """A sink obtained mid-close would spawn a drain nobody gathers."""

    class _SlowCloseStore(MemoryStore):
        def __init__(
            self,
            path: PathInfo,
            specs: Mapping[str, StreamSpec],
            gate: asyncio.Event,
        ) -> None:
            super().__init__(path, specs)
            self._gate = gate

        async def close(self) -> None:
            await self._gate.wait()
            await super().close()

    class _SlowCloseIO(MemoryIO):
        def __init__(self) -> None:
            super().__init__()
            self.gate = asyncio.Event()

        async def open(
            self, path: PathInfo, specs: Mapping[str, StreamSpec]
        ) -> OpenStore:
            store = _SlowCloseStore(path, specs, self.gate)
            self.stores.append(store)
            return store

    io = _SlowCloseIO()
    storage = BaseStorage(io=io, path_provider=provider)
    storage.register(spec("det", capacity=1))
    sink = storage.sink("det")
    await sink.put(frame())
    close_task = asyncio.create_task(storage.close())
    while not storage._open_lock.locked():
        await asyncio.sleep(0)
    with pytest.raises(StoreStateError):
        storage.sink("late")
    io.gate.set()
    await close_task


async def test_multiple_drain_failures_raise_exception_group(
    provider: SessionPathProvider,
) -> None:
    """Two failing drains surface both errors, not just the first."""

    class _FailingWriteStore(MemoryStore):
        async def write(self, data_key: str, frame: npt.NDArray[Any]) -> None:
            raise OSError(f"disk on fire for {data_key}")

    class _FailingWriteIO(MemoryIO):
        async def open(
            self, path: PathInfo, specs: Mapping[str, StreamSpec]
        ) -> OpenStore:
            store = _FailingWriteStore(path, specs)
            self.stores.append(store)
            return store

    storage = BaseStorage(io=_FailingWriteIO(), path_provider=provider)
    storage.register(spec("a", capacity=1))
    storage.register(spec("b", capacity=1))
    sink_a = storage.sink("a")
    sink_b = storage.sink("b")
    await sink_a.put(frame())
    await sink_b.put(frame())
    with pytest.raises(ExceptionGroup) as excinfo:
        await storage.close()
    assert len(excinfo.value.exceptions) == 2
    assert all(isinstance(exc, OSError) for exc in excinfo.value.exceptions)


async def test_orphan_sweep_close_failure_propagates(
    provider: SessionPathProvider,
) -> None:
    """A store opened without sinks whose close fails raises from close()."""

    class _FailingCloseStore(MemoryStore):
        async def close(self) -> None:
            raise OSError("close boom")

    class _FailingCloseIO(MemoryIO):
        async def open(
            self, path: PathInfo, specs: Mapping[str, StreamSpec]
        ) -> OpenStore:
            store = _FailingCloseStore(path, specs)
            self.stores.append(store)
            return store

    storage = BaseStorage(io=_FailingCloseIO(), path_provider=provider)
    storage.register(spec("det", capacity=1))
    await storage.open()
    with pytest.raises(OSError, match="close boom"):
        await storage.close()
    # teardown completed despite the failure: a fresh burst is possible
    storage.register(spec("det", capacity=1))
    await storage.close()


async def test_close_cancelled_during_sweep_propagates(
    provider: SessionPathProvider,
) -> None:
    """Cancelling close() mid-sweep re-raises cancellation, never converts it."""

    class _SlowCloseStore(MemoryStore):
        def __init__(
            self,
            path: PathInfo,
            specs: Mapping[str, StreamSpec],
            gate: asyncio.Event,
        ) -> None:
            super().__init__(path, specs)
            self._gate = gate

        async def close(self) -> None:
            await self._gate.wait()
            await super().close()

    class _SlowCloseIO(MemoryIO):
        def __init__(self) -> None:
            super().__init__()
            self.gate = asyncio.Event()

        async def open(
            self, path: PathInfo, specs: Mapping[str, StreamSpec]
        ) -> OpenStore:
            store = _SlowCloseStore(path, specs, self.gate)
            self.stores.append(store)
            return store

    io = _SlowCloseIO()
    storage = BaseStorage(io=io, path_provider=provider)
    storage.register(spec("det", capacity=1))
    await storage.open()
    close_task = asyncio.create_task(storage.close())
    while not storage._open_lock.locked():
        await asyncio.sleep(0)
    close_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close_task
