from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from redsun.storage import SessionPathProvider, StreamSpec
from redsun.storage._base import BaseStorage
from redsun.storage._fsm import InvalidStoreState, StorageState
from redsun.storage.backends._memory import MemoryIO

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

    import numpy.typing as npt


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
