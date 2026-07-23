from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from redsun.storage import SessionPathProvider, StreamSpec
from redsun.storage._base import BaseStorage
from redsun.storage.backends._acquire_zarr import DTYPE_MAP, AcquireZarrIO

if TYPE_CHECKING:
    from typing import Any

    import numpy.typing as npt

    from redsun.storage._base import FrameSender


def spec(
    data_key: str,
    capacity: int | None = None,
    shape: tuple[int, int] = (8, 8),
    dtype: str = "uint16",
) -> StreamSpec:
    return StreamSpec(data_key=data_key, shape=shape, dtype=dtype, capacity=capacity)


def frame(
    fill: int = 0, shape: tuple[int, int] = (8, 8), dtype: str = "uint16"
) -> npt.NDArray[Any]:
    return np.full(shape, fill, dtype=np.dtype(dtype))


async def drive(
    sink: FrameSender,
    count: int,
    shape: tuple[int, int] = (8, 8),
    dtype: str = "uint16",
) -> None:
    """Send `count` frames, absorbing the terminal StopAsyncIteration."""
    try:
        for i in range(count):
            await sink.asend(frame(i, shape=shape, dtype=dtype))
    except StopAsyncIteration:
        pass


@pytest.fixture
def provider(tmp_path: Path) -> SessionPathProvider:
    return SessionPathProvider(base_dir=tmp_path, session="test_session")


@pytest.fixture
def io() -> AcquireZarrIO:
    return AcquireZarrIO()


@pytest.fixture
def storage(io: AcquireZarrIO, provider: SessionPathProvider) -> BaseStorage:
    return BaseStorage(io=io, path_provider=provider)


class TestArraySettings:
    def test_spatial_chunks_divide_shape(self, io: AcquireZarrIO) -> None:
        settings = io._array_settings(spec("cam", shape=(64, 32)))
        t, y, x = settings.dimensions

        assert (y.array_size_px, x.array_size_px) == (64, 32)
        assert (y.chunk_size_px, x.chunk_size_px) == (16, 8)

    def test_spatial_chunks_clamp_to_one_pixel(self) -> None:
        io = AcquireZarrIO(chunk_divisor=64)
        settings = io._array_settings(spec("cam", shape=(8, 8)))
        _, y, x = settings.dimensions

        assert (y.chunk_size_px, x.chunk_size_px) == (1, 1)

    @pytest.mark.parametrize("capacity", [1, 4, 100])
    def test_bounded_capacity_sets_time_extent(
        self, io: AcquireZarrIO, capacity: int
    ) -> None:
        settings = io._array_settings(spec("cam", capacity=capacity))

        assert settings.dimensions[0].array_size_px == capacity

    def test_unbounded_capacity_maps_to_zero_extent(self, io: AcquireZarrIO) -> None:
        """acquire-zarr treats a zero time extent as append-forever."""
        settings = io._array_settings(spec("cam", capacity=None))

        assert settings.dimensions[0].array_size_px == 0

    @pytest.mark.parametrize("dtype", sorted(DTYPE_MAP))
    def test_every_mapped_dtype_is_accepted(
        self, io: AcquireZarrIO, dtype: str
    ) -> None:
        settings = io._array_settings(spec("cam", dtype=dtype))

        assert settings.data_type == DTYPE_MAP[dtype]

    def test_unmapped_dtype_raises(self, io: AcquireZarrIO) -> None:
        with pytest.raises(KeyError):
            io._array_settings(spec("cam", dtype="complex64"))

    def test_output_key_is_the_data_key(self, io: AcquireZarrIO) -> None:
        assert io._array_settings(spec("median")).output_key == "median"


class TestResourceInfo:
    def test_chunk_shape_matches_array_settings(self, io: AcquireZarrIO) -> None:
        """The document must describe the true on-disk layout."""
        target = spec("cam", shape=(64, 32))
        info = io.resource_info(target)
        _, y, x = io._array_settings(target).dimensions

        assert info.chunk_shape == (1, y.chunk_size_px, x.chunk_size_px)

    def test_chunk_t_is_reflected(self) -> None:
        io = AcquireZarrIO(chunk_t=7)

        assert io.resource_info(spec("cam")).chunk_shape[0] == 7

    def test_dtype_numpy_is_a_valid_dtype_string(self, io: AcquireZarrIO) -> None:
        info = io.resource_info(spec("cam", dtype="float32"))

        assert np.dtype(info.dtype_numpy) == np.dtype("float32")

    def test_parameters_carry_the_key_path(self, io: AcquireZarrIO) -> None:
        assert io.resource_info(spec("median")).parameters == {"path": "median"}


class TestUri:
    def test_uri_ends_with_extension(
        self, io: AcquireZarrIO, provider: SessionPathProvider
    ) -> None:
        path = provider()

        assert io.uri(path, "cam").endswith(f"{path.filename}.zarr")

    def test_uri_is_shared_across_keys(
        self, io: AcquireZarrIO, provider: SessionPathProvider
    ) -> None:
        """All keys of a burst live in one store, so the URI cannot differ."""
        path = provider()

        assert io.uri(path, "cam") == io.uri(path, "median")


class TestRoundTrip:
    async def test_bounded_burst_writes_capacity_frames(
        self, storage: BaseStorage, tmp_path: Path
    ) -> None:
        await storage.register(spec("cam", capacity=4))
        sink = await storage("cam")
        await drive(sink, 4)
        await storage.reset()

        assert len(list(tmp_path.rglob("*.zarr"))) == 1

    async def test_multi_key_burst_shares_one_store(
        self, storage: BaseStorage, tmp_path: Path
    ) -> None:
        await storage.register(spec("cam", capacity=3))
        await storage.register(spec("median", capacity=3))
        cam = await storage("cam")
        median = await storage("median")
        await drive(cam, 3)
        await drive(median, 3)
        await storage.reset()

        assert len(list(tmp_path.rglob("*.zarr"))) == 1

    async def test_consecutive_bursts_write_distinct_stores(
        self, storage: BaseStorage, tmp_path: Path
    ) -> None:
        for _ in range(2):
            await storage.register(spec("cam", capacity=2))
            sink = await storage("cam")
            await drive(sink, 2)
            await storage.reset()

        assert len(list(tmp_path.rglob("*.zarr"))) == 2

    async def test_unbounded_burst_accepts_arbitrary_frames(
        self, storage: BaseStorage, tmp_path: Path
    ) -> None:
        await storage.register(spec("cam", capacity=None))
        sink = await storage("cam")
        await drive(sink, 7)
        await storage.reset()

        assert len(list(tmp_path.rglob("*.zarr"))) == 1

    async def test_reset_without_frames_writes_nothing(
        self, storage: BaseStorage, tmp_path: Path
    ) -> None:
        await storage.register(spec("cam"))
        await storage("cam")
        await storage.reset()

        assert list(tmp_path.rglob("*.zarr")) == []

    async def test_oversized_frame_is_split_not_rejected(
        self, storage: BaseStorage, tmp_path: Path
    ) -> None:
        """acquire-zarr reinterprets the buffer instead of validating shape."""
        await storage.register(spec("cam", shape=(8, 8), capacity=None))
        sink = await storage("cam")
        await sink.asend(frame(0, shape=(16, 16)))
        await storage.reset()

        assert len(list(tmp_path.rglob("*.zarr"))) == 1
