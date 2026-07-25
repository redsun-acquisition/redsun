from __future__ import annotations

import pytest

from redsun.storage import StreamSpec
from redsun.storage._router import FrameRouter


def spec(data_key: str) -> StreamSpec:
    return StreamSpec(data_key=data_key, shape=(4, 4), dtype="uint16", capacity=1)


def test_add_duplicate_key_raises() -> None:
    router = FrameRouter()
    router.add(spec("det"))
    with pytest.raises(KeyError):
        router.add(spec("det"))


def test_delete_missing_key_is_noop() -> None:
    router = FrameRouter()
    router.add(spec("det"))
    router.delete("ghost")  # must not raise
    assert set(router.spec.keys()) == {"det"}
    router.delete("det")
    assert router.spec == {}


async def test_mark_written_advances_only_target_key() -> None:
    router = FrameRouter()
    router.add(spec("a"))
    router.add(spec("b"))
    router.mark_written("a")
    router.mark_written("a")
    assert await router.signals["a"].get_value() == 2
    assert await router.signals["b"].get_value() == 0
