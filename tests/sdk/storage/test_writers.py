"""Derived-product writers add to, or write beside, a store already written."""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from typing import TYPE_CHECKING

import numpy as np
import pytest

from redsun.storage.writers import (
    WriterError,
    ome_zarr,
    zarr,
)
from redsun.storage.writers._base import root_attributes as attributes

if TYPE_CHECKING:
    from pathlib import Path


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


def test_ome_zarr_adds_a_named_image_to_a_plain_root(ngff_store: Path) -> None:
    """A plain root holds one image per key, so the product joins them."""
    store = ngff_store

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


def test_ome_zarr_writes_a_sibling_beside_a_plate(tmp_path: Path) -> None:
    """A root holding a plate keeps it, as an image root does."""
    store = tmp_path / "plate.ome.zarr"
    store.mkdir()
    plate = {"version": "0.5", "plate": {"columns": [], "rows": [], "wells": []}}
    (store / "zarr.json").write_text(
        json.dumps(
            {"zarr_format": 3, "node_type": "group", "attributes": {"ome": plate}}
        ),
        encoding="utf-8",
    )

    product = ome_zarr.write(
        store.as_uri(), data_key="det_median", data=np.ones((4, 4), np.uint16)
    )

    assert product == (tmp_path / "plate_det_median.ome.zarr").as_uri()
    assert attributes(store) == {"ome": plate}


def test_both_writers_take_the_same_arguments() -> None:
    """A caller picks the module by mimetype, so the call cannot differ."""
    assert inspect.signature(zarr.write) == inspect.signature(ome_zarr.write)


@pytest.mark.parametrize(
    ("package", "module", "extra"),
    [
        ("acquire_zarr", "zarr", "redsun[zarr]"),
        ("ome_writers", "ome_zarr", "redsun[ome-zarr]"),
    ],
)
def test_a_missing_package_names_the_extra(
    package: str, module: str, extra: str
) -> None:
    """Importing the writer says what to install, in a process without the package."""
    # None in sys.modules makes any import of the package raise ImportError
    code = (
        f"import sys; sys.modules[{package!r}] = None; "
        f"import redsun.storage.writers.{module}"
    )

    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )

    assert result.returncode != 0
    assert f"ImportError: {package.replace('_', '-')}" in result.stderr
    assert f"pip install {extra}" in result.stderr
