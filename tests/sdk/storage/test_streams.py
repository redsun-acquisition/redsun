"""A stream appends frames to the arrays it was opened with, and to nothing else."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

from redsun.storage.writers import WriterError, _acquire_zarr, _ome_writers
from redsun.storage.writers._base import ArrayShape

if TYPE_CHECKING:
    from pathlib import Path

zarr_python = pytest.importorskip("zarr")

FRAME = ArrayShape.of((4, 4), np.uint16)


def read(store: Path, key: str) -> np.ndarray[Any, Any]:
    """Return the whole array stored under *key* in *store*."""
    return np.asarray(zarr_python.open_array(store, path=key, mode="r")[:])


def attributes(path: Path) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (path / "zarr.json").read_text(encoding="utf-8")
    )
    node_attributes: dict[str, Any] = document["attributes"]
    return node_attributes


def test_a_stream_appends_to_each_of_its_keys_in_turn(tmp_path: Path) -> None:
    """Every key is declared at open; frames then land in their own arrays."""
    stream = _acquire_zarr.Stream(
        tmp_path / "run.zarr", {"a": FRAME, "b": FRAME}, is_ngff=False
    )
    for index in range(3):
        stream.append("a", np.full((4, 4), index, np.uint16))
        stream.append("b", np.full((2, 4, 4), 10 + index, np.uint16))
    stream.close()

    a, b = read(tmp_path / "run.zarr", "a"), read(tmp_path / "run.zarr", "b")
    assert a.shape == (3, 4, 4)
    assert b.shape == (6, 4, 4)
    assert a[:, 0, 0].tolist() == [0, 1, 2]
    assert b[:, 0, 0].tolist() == [10, 10, 11, 11, 12, 12]


@pytest.mark.parametrize(
    ("data_key", "data", "phrase"),
    [
        ("b", np.zeros((4, 4), np.uint16), "opened with ['a']"),
        ("a", np.zeros((4, 4), np.float32), "declared as uint16"),
        ("a", np.zeros((4, 5), np.uint16), "frames of shape (4, 4)"),
    ],
)
def test_a_stream_refuses_what_it_was_not_opened_with(
    tmp_path: Path, data_key: str, data: Any, phrase: str
) -> None:
    """A key, dtype or shape the stream does not know is named in the refusal."""
    stream = _acquire_zarr.Stream(tmp_path / "run.zarr", {"a": FRAME}, is_ngff=False)
    try:
        with pytest.raises(WriterError, match=re.escape(phrase)):
            stream.append(data_key, data)
    finally:
        stream.close()


def test_an_ome_stream_holds_the_frames_it_was_told(tmp_path: Path) -> None:
    """The layout is the whole image; four frames come back as ``(4, y, x)``."""
    store = tmp_path / "product.ome.zarr"
    stream = _ome_writers.Stream(
        store, {"det_sum": ArrayShape.of((4, 4, 4), np.uint16)}
    )
    stream.append("det_sum", np.arange(64, dtype=np.uint16).reshape(4, 4, 4))
    stream.close()

    image = read(store, "0")
    assert image.shape == (4, 4, 4)
    assert image[3, 3, 3] == 63
    assert [
        axis["name"] for axis in attributes(store)["ome"]["multiscales"][0]["axes"]
    ] == ["z", "y", "x"]
