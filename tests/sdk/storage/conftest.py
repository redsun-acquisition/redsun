"""Stores as a device writes them, for the products written against them."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import numpy as np
import ome_writers as ow
import pytest

from redsun.storage.writers import _acquire_zarr
from redsun.storage.writers._base import ArrayShape

if TYPE_CHECKING:
    from pathlib import Path

FRAME = ArrayShape.of((4, 4), np.uint16)


def attributes(path: Path) -> dict[str, Any]:
    """Return the attributes of the Zarr group at *path*."""
    document: dict[str, Any] = json.loads(
        (path / "zarr.json").read_text(encoding="utf-8")
    )
    node_attributes: dict[str, Any] = document["attributes"]
    return node_attributes


def open_key(store: Path, data_key: str, *, is_ngff: bool) -> None:
    """Write two zero frames under *data_key* in *store*, as a device would."""
    stream = _acquire_zarr.Stream(store, {data_key: FRAME}, is_ngff=is_ngff)
    stream.append(data_key, np.zeros((2, 4, 4), np.uint16))
    stream.close()


@pytest.fixture
def plain_store(tmp_path: Path) -> Path:
    """Give a store whose root is a plain group, as `acquire-zarr` writes one."""
    store = tmp_path / "run.zarr"
    open_key(store, "det", is_ngff=False)
    return store


@pytest.fixture
def ngff_store(tmp_path: Path) -> Path:
    """Give a store whose root is a plain group holding one NGFF image per key."""
    store = tmp_path / "ngff.zarr"
    open_key(store, "det", is_ngff=True)
    return store


@pytest.fixture
def image_store(tmp_path: Path) -> Path:
    """Give a store whose root is the image, as `ome-writers` writes one."""
    store = tmp_path / "run42.ome.zarr"
    settings = ow.AcquisitionSettings(
        root_path=str(store),
        dimensions=tuple(ow.dims_from_standard_axes({"t": 2, "y": 4, "x": 4})),
        dtype="uint16",
        format=ow.OmeZarrFormat(backend="acquire-zarr"),
    )
    with ow.create_stream(settings) as stream:
        for frame in np.zeros((2, 4, 4), np.uint16):
            stream.append(frame)
    return store
