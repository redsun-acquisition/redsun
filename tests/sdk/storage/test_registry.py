from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from redsun.storage import (
    BaseStorage,
    SessionPathProvider,
    StreamSpec,
    clear_registry,
    get_storage,
    register_storage,
    reset_group,
)
from redsun.storage.backends._memory import MemoryIO

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def storage(tmp_path: Path) -> BaseStorage:
    provider = SessionPathProvider(base_dir=tmp_path, session="test_session")
    return BaseStorage(io=MemoryIO(), path_provider=provider)


def test_register_and_get_roundtrip(storage: BaseStorage) -> None:
    register_storage("acq", storage)
    assert get_storage("acq", storage.mimetype) is storage


def test_duplicate_registration_raises(storage: BaseStorage) -> None:
    register_storage("acq", storage)
    with pytest.raises(KeyError):
        register_storage("acq", storage)


def test_missing_key_raises_loudly() -> None:
    with pytest.raises(KeyError):
        get_storage("nowhere", "application/x-memory")


async def test_reset_group_closes_with_drop_but_keeps_registration(
    storage: BaseStorage,
) -> None:
    register_storage("acq", storage)
    storage.register(
        StreamSpec(data_key="det", shape=(4, 4), dtype="uint16", capacity=None)
    )
    sink = storage.sink("det")
    await sink.put(np.zeros((4, 4), dtype=np.uint16))
    await reset_group("acq")
    # instance still resolvable and usable for a fresh burst
    assert get_storage("acq", storage.mimetype) is storage
    storage.register(
        StreamSpec(data_key="det", shape=(4, 4), dtype="uint16", capacity=1)
    )
