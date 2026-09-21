"""A product's place is decided by the store's mimetype and what its root holds."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from redsun.storage.writers import WriterError
from redsun.storage.writers._placement import OME_ZARR, ZARR, placement

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def plate_store(tmp_path: Path) -> Path:
    """Give a store whose root holds a plate, with no image to append to."""
    store = tmp_path / "plate.ome.zarr"
    store.mkdir()
    plate = {"version": "0.5", "plate": {"columns": [], "rows": [], "wells": []}}
    (store / "zarr.json").write_text(
        json.dumps(
            {"zarr_format": 3, "node_type": "group", "attributes": {"ome": plate}}
        ),
        encoding="utf-8",
    )
    return store


@pytest.mark.parametrize(
    ("store", "mimetype"),
    [("plain_store", ZARR), ("plain_store", OME_ZARR), ("ngff_store", OME_ZARR)],
)
def test_a_plain_root_takes_the_product_as_a_key(
    request: pytest.FixtureRequest, store: str, mimetype: str
) -> None:
    """The stream opens on the store itself, and the product's URI is the store's."""
    path: Path = request.getfixturevalue(store)

    placed = placement(path.as_uri(), mimetype, "det_median")

    assert placed is not None
    assert placed.path == path
    assert placed.uri == path.as_uri()
    assert placed.streamed


@pytest.mark.parametrize("store", ["image_store", "plate_store"])
def test_an_ngff_root_sends_the_product_beside_it(
    request: pytest.FixtureRequest, store: str
) -> None:
    """A store of its own, named after the acquisition and the product, written whole."""
    path: Path = request.getfixturevalue(store)

    placed = placement(path.as_uri(), OME_ZARR, "det_median")

    assert placed is not None
    assert placed.path == path.parent / f"{path.name.split('.')[0]}_det_median.ome.zarr"
    assert placed.uri == placed.path.as_uri()
    assert not placed.streamed


def test_a_plain_zarr_store_with_an_ngff_root_is_refused(image_store: Path) -> None:
    """The refusal protects the root's metadata, and names the mimetype to use."""
    with pytest.raises(WriterError, match=OME_ZARR):
        placement(image_store.as_uri(), ZARR, "det_median")


def test_an_unknown_mimetype_has_no_placement(plain_store: Path) -> None:
    assert placement(plain_store.as_uri(), "image/tiff", "det_median") is None
