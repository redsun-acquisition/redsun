"""Derived-product writers add to, or write beside, a store already written."""

from __future__ import annotations

import inspect
import json
from typing import TYPE_CHECKING, Any

import numpy as np
import ome_writers as ow
import pytest

from redsun.storage.writers import WriterError, ome_zarr, zarr
from redsun.storage.writers._acquire_zarr import append_key

if TYPE_CHECKING:
    from pathlib import Path


def attributes(path: Path) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (path / "zarr.json").read_text(encoding="utf-8")
    )
    node_attributes: dict[str, Any] = document["attributes"]
    return node_attributes


@pytest.fixture
def plain_store(tmp_path: Path) -> Path:
    """Give a store whose root is a plain group, as `acquire-zarr` writes one."""
    store = tmp_path / "run.zarr"
    append_key(
        store, data_key="det", data=np.zeros((2, 4, 4), np.uint16), is_ngff=False
    )
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


def test_a_key_is_added_to_a_plain_root(plain_store: Path) -> None:
    """The product goes in the store the acquisition wrote, so the URI is the same."""
    product = zarr.write(
        plain_store.as_uri(),
        data_key="det_median",
        data=np.ones((4, 4), np.uint16),
        metadata={"derived_from": "det"},
    )

    assert product == plain_store.as_uri()
    assert sorted(entry.name for entry in plain_store.iterdir()) == [
        "det",
        "det_median",
        "zarr.json",
    ]
    # never the root's, which a stream closing on the store rewrites
    assert attributes(plain_store / "det_median") == {"derived_from": "det"}
    assert attributes(plain_store) == {}


def test_an_image_root_is_refused_with_its_metadata_intact(image_store: Path) -> None:
    """The refusal is the point: a key added here empties the root's attributes."""
    before = list(attributes(image_store))

    with pytest.raises(WriterError, match="ome_zarr"):
        zarr.write(
            image_store.as_uri(), data_key="det_median", data=np.ones((4, 4), np.uint16)
        )

    assert list(attributes(image_store)) == before
    assert "ome" in before


def test_ome_zarr_adds_a_named_image_to_a_plain_root(tmp_path: Path) -> None:
    """A plain root holds one image per key, so the product joins them."""
    store = tmp_path / "ngff.zarr"
    append_key(store, data_key="det", data=np.zeros((2, 4, 4), np.uint16), is_ngff=True)

    product = ome_zarr.write(
        store.as_uri(),
        data_key="det_median",
        data=np.ones((4, 4), np.uint16),
        metadata={"derived_from": "det"},
    )

    assert product == store.as_uri()
    assert "ome" in attributes(store / "det_median")
    assert attributes(store / "det_median")["derived_from"] == "det"


def test_ome_zarr_writes_a_sibling_beside_an_image_root(image_store: Path) -> None:
    """The acquisition keeps its metadata, and the product is a store of its own."""
    product = ome_zarr.write(
        image_store.as_uri(),
        data_key="det_median",
        data=np.ones((4, 4), np.uint16),
        metadata={"derived_from": "det"},
    )

    sibling = image_store.parent / "run42_det_median.ome.zarr"
    assert product == sibling.as_uri()
    assert product != image_store.as_uri()
    assert "ome" in attributes(image_store)
    assert attributes(sibling)["redsun"] == {"derived_from": "det"}
    assert [
        axis["name"] for axis in attributes(sibling)["ome"]["multiscales"][0]["axes"]
    ] == ["y", "x"]


def test_both_writers_take_the_same_arguments() -> None:
    """A caller picks the module by mimetype, so the call cannot differ."""
    assert inspect.signature(zarr.write) == inspect.signature(ome_zarr.write)


def test_a_missing_package_names_the_extra(
    plain_store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller is told what to install, not given an ImportError."""

    def absent(name: str) -> Any:
        raise ImportError(name)

    monkeypatch.setattr("importlib.import_module", absent)

    with pytest.raises(WriterError, match=r"redsun\[zarr\]"):
        zarr.write(
            plain_store.as_uri(), data_key="det_median", data=np.ones((4, 4), np.uint16)
        )
