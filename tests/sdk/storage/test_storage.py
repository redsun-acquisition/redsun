from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import numpy as np
import pytest

from redsun.storage import SessionPathProvider, StreamSpec
from redsun.storage._base import BaseStorage, OpenStore
from redsun.storage._fsm import InvalidStoreState, StorageState
from redsun.storage.backends._memory import MemoryIO, MemoryStore

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path
    from typing import Any

    import numpy.typing as npt
    from ophyd_async.core import PathInfo

    from redsun.storage._base import FrameSender


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


class TestSingleKeyStorage:
    async def test_single_write(self, storage: BaseStorage, io: MemoryIO) -> None:
        await storage.register(spec("cam"))
        assert io.stores == []

        sink = await storage("cam")
        await sink.asend(frame())
        assert len(io.stores) == 1
        assert io.stores[0].calls[0] == ("write", "cam")

    async def test_open_carries_full_spec_map(
        self, storage: BaseStorage, io: MemoryIO
    ) -> None:
        await storage.register(spec("cam"))
        await storage.register(spec("median"))
        cam = await storage("cam")
        await cam.asend(frame())

        assert len(io.stores) == 1
        assert io.stores[0].calls[0] == ("write", "cam")

        assert set(io.stores[0].specs.keys()) == {"cam", "median"}

    async def test_register_after_seal(
        self, storage: BaseStorage, io: MemoryIO
    ) -> None:
        await storage.register(spec("cam"))
        sink = await storage("cam")
        await sink.asend(frame())
        with pytest.raises(InvalidStoreState):
            await storage.register(spec("median"))

    async def test_generator_close(self, storage: BaseStorage, io: MemoryIO) -> None:
        await storage.register(spec("cam"))
        sink = await storage("cam")
        await sink.asend(frame())
        await sink.aclose()
        assert ("release", "cam") in io.stores[0].calls
        assert io.stores[0].calls[-1] == ("close", "")
        assert storage._fsm.state == StorageState.UNSEALED

    async def test_close_no_frame(self, storage: BaseStorage, io: MemoryIO) -> None:
        await storage.register(spec("cam"))
        sink = await storage("cam")
        await sink.aclose()
        assert len(io.stores) == 0
        assert storage._fsm.state == StorageState.UNSEALED


class TestCapacity:
    @pytest.mark.parametrize("capacity", [1, 2, 3, 5])
    async def test_bounded_capacity(
        self, storage: BaseStorage, io: MemoryIO, capacity: int
    ) -> None:
        await storage.register(spec("cam", capacity=capacity))
        sink = await storage("cam")

        for i in range(capacity - 1):
            await sink.asend(frame(i))

        with pytest.raises(StopAsyncIteration):
            await sink.asend(frame(capacity - 1))

        assert len(io.stores) == 1
        assert len(io.stores[0].arrays["cam"]) == capacity

    async def test_unbounded_capacity(self, storage: BaseStorage, io: MemoryIO) -> None:
        await storage.register(spec("cam", capacity=None))
        sink = await storage("cam")
        for i in range(20):
            await sink.asend(frame(i))
        assert len(io.stores) == 1
        assert len(io.stores[0].arrays["cam"]) == 20

    async def test_zero_capacity_rejected(self, storage: BaseStorage) -> None:
        with pytest.raises(ValueError):
            await storage.register(spec("cam", capacity=0))


class TestMultiKey:
    async def test_close_until_all_released(
        self, storage: BaseStorage, io: MemoryIO
    ) -> None:
        await storage.register(spec("cam"))
        await storage.register(spec("median"))

        cam = await storage("cam")
        median = await storage("median")

        await cam.asend(frame())
        await median.asend(frame())

        await cam.aclose()
        assert ("release", "cam") in io.stores[0].calls
        assert ("release", "median") not in io.stores[0].calls
        assert io.stores[0].calls[-1] != ("close", "")
        assert storage._fsm.state is StorageState.OPEN

        await median.aclose()
        assert ("release", "median") in io.stores[0].calls
        assert io.stores[0].calls[-1] == ("close", "")
        assert storage._fsm.state is StorageState.UNSEALED


class TestCounterOrder:
    @pytest.mark.parametrize("num_frames", [1, 5, 10, 20])
    async def test_counter_advances_on_write(
        self, storage: BaseStorage, num_frames: int
    ) -> None:
        await storage.register(spec("cam"))
        counter = storage.signal_for("cam")
        sink = await storage("cam")

        for i in range(num_frames):
            await sink.asend(frame(i))
            assert await counter.get_value() == i + 1

    async def test_counter_does_not_advance_until_write_returns(
        self, provider: SessionPathProvider
    ) -> None:
        """Ensure that the counter does not advance until the write operation completes."""
        io = GatedIO()

        async def send_frame_with_delay(
            sink: FrameSender, frame: npt.NDArray[Any], delay: float
        ) -> None:
            await asyncio.sleep(delay)
            await sink.asend(frame)

        storage = BaseStorage(io=io, path_provider=provider)
        await storage.register(spec("cam"))
        counter = storage.signal_for("cam")
        sink = await storage("cam")

        task = asyncio.create_task(send_frame_with_delay(sink, frame(1), delay=0.1))

        await asyncio.sleep(
            0
        )  # yield control to the event loop to ensure the task starts
        assert await counter.get_value() == 0  # Counter should not advance yet
        assert not task.done()

        io.set_gate()  # Allow the write to proceed
        await asyncio.wait_for(task, timeout=0.5)
        assert (
            await counter.get_value() == 1
        )  # Counter should advance after write completes


class TestConcurrentSeal: ...
