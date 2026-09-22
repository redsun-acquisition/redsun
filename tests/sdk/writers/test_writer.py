"""A writer follows a run's documents and places what a component hands it."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

from redsun.writers import Writer, WriterError
from redsun.writers._base import root_attributes as attributes

if TYPE_CHECKING:
    from pathlib import Path


def shape_of(path: Path) -> list[int]:
    """Return the shape a Zarr array's metadata records."""
    document: dict[str, Any] = json.loads(
        (path / "zarr.json").read_text(encoding="utf-8")
    )
    shape: list[int] = document["shape"]
    return shape


def run(writer: Writer, store: Path, mimetype: str, *, start: bool = True) -> str:
    """Send *writer* a descriptor and a resource naming ``det`` and its store.

    A run is started first unless *start* is false. Returns the run's uid.
    """
    if start:
        writer("start", {"uid": "run-1", "time": 0.0})
    writer(
        "descriptor",
        {
            "uid": "desc-1",
            "run_start": "run-1",
            "name": "primary",
            "data_keys": {
                "det": {
                    "source": "det",
                    "dtype": "array",
                    "dtype_numpy": "<u2",
                    "shape": [1, 4, 4],
                    "external": "STREAM:",
                }
            },
        },
    )
    writer(
        "stream_resource",
        {
            "uid": "res-1",
            "run_start": "run-1",
            "data_key": "det",
            "mimetype": mimetype,
            "uri": store.as_uri(),
            "parameters": {},
        },
    )
    return "run-1"


def test_a_derived_product_lands_in_its_source_store_with_both_mappings(
    plain_store: Path,
) -> None:
    """The run gives the layout and the store; the component gives the data and its mapping."""
    writer = Writer()
    writer.derive("det_median", source="det")
    uid = run(writer, plain_store, "application/x-zarr")

    product = writer.write(
        "det_median", np.ones((4, 4), np.uint16), metadata={"derived_from": "det"}
    )
    writer(
        "stop",
        {"uid": "stop-1", "run_start": uid, "time": 2.0, "exit_status": "success"},
    )

    assert product == plain_store.as_uri()
    assert shape_of(plain_store / "det_median") == [1, 4, 4]
    written = attributes(plain_store / "det_median")
    assert written["derived_from"] == "det"
    assert written["redsun"]["run_start"] == uid
    assert written["redsun"]["source"] == "det"
    assert written["redsun"]["resource_uri"] == plain_store.as_uri()
    assert "written" in written["redsun"]
    assert attributes(plain_store) == {}


def test_a_streamed_product_holds_one_frame_per_append(plain_store: Path) -> None:
    """Appended per event, the product is one array of as many frames."""
    writer = Writer()
    writer.derive("det_filtered", source="det")
    run(writer, plain_store, "application/x-zarr")
    for _ in range(5):
        writer.append("det_filtered", np.ones((4, 4), np.uint16))

    writer.close()

    assert shape_of(plain_store / "det_filtered") == [5, 4, 4]


def test_a_declared_product_needs_no_documents(tmp_path: Path) -> None:
    """A layout and a store given up front are enough to write."""
    store = tmp_path / "products.zarr"
    writer = Writer()
    writer.declare("mask", shape=(4, 4), dtype=np.uint8, store=store.as_uri())

    product = writer.write("mask", np.zeros((4, 4), np.uint8))
    writer.close()

    assert product == store.as_uri()
    assert shape_of(store / "mask") == [1, 4, 4]
    assert attributes(store / "mask")["redsun"]["run_start"] is None


def test_an_ome_zarr_store_with_a_plain_root_takes_the_product_as_an_image(
    ngff_store: Path,
) -> None:
    """A plain root holds one image per key, so the product joins them as one."""
    writer = Writer()
    writer.derive("det_median", source="det")
    run(writer, ngff_store, "application/x-ome-zarr")

    product = writer.write(
        "det_median", np.ones((4, 4), np.uint16), metadata={"derived_from": "det"}
    )
    writer.close()

    assert product == ngff_store.as_uri()
    assert "ome" in attributes(ngff_store / "det_median")
    assert attributes(ngff_store / "det_median")["derived_from"] == "det"


def test_an_image_root_gets_a_sibling_written_whole(image_store: Path) -> None:
    """A store of its own, finished at once, keeps the acquisition's metadata intact."""
    writer = Writer()
    writer.derive("det_median", source="det")
    run(writer, image_store, "application/x-ome-zarr")

    product = writer.write(
        "det_median", np.ones((4, 4), np.uint16), metadata={"derived_from": "det"}
    )

    sibling = image_store.parent / "run42_det_median.ome.zarr"
    assert product == sibling.as_uri()
    assert "ome" in attributes(image_store)
    assert attributes(sibling)["derived_from"] == "det"
    assert attributes(sibling)["redsun"]["source"] == "det"
    with pytest.raises(WriterError, match="use write"):
        writer.append("det_median", np.ones((4, 4), np.uint16))


@pytest.mark.parametrize(
    ("documents", "phrase"),
    [
        ("none", "was not declared"),
        ("no descriptor", "no layout yet"),
        ("no resource", "no store yet"),
    ],
)
def test_a_product_without_its_layout_or_store_is_refused_naming_what_is_missing(
    plain_store: Path, documents: str, phrase: str
) -> None:
    writer = Writer()
    if documents != "none":
        writer.derive("det_median", source="det")
    writer("start", {"uid": "run-1", "time": 0.0})
    if documents == "no resource":
        writer(
            "descriptor",
            {
                "uid": "desc-1",
                "run_start": "run-1",
                "name": "primary",
                "data_keys": {
                    "det": {
                        "source": "det",
                        "dtype": "array",
                        "dtype_numpy": "<u2",
                        "shape": [1, 4, 4],
                        "external": "STREAM:",
                    }
                },
            },
        )

    with pytest.raises(WriterError, match=phrase):
        writer.append("det_median", np.ones((4, 4), np.uint16))


def test_a_product_declared_after_its_store_opened_is_refused(
    plain_store: Path,
) -> None:
    """Every array of a store is sized at open, so a late product cannot join."""
    writer = Writer()
    writer.derive("det_filtered", source="det")
    run(writer, plain_store, "application/x-zarr")
    writer.append("det_filtered", np.ones((4, 4), np.uint16))
    writer.derive("det_median", source="det")
    run(writer, plain_store, "application/x-zarr", start=False)

    with pytest.raises(WriterError, match="opened without 'det_median'"):
        writer.write("det_median", np.ones((4, 4), np.uint16))
    writer.close()


def test_a_second_run_reuses_the_writer(tmp_path: Path) -> None:
    """What one run filled in is forgotten at its stop, and the next run fills it again."""
    writer = Writer()
    writer.derive("det_median", source="det")
    first, second = tmp_path / "first.zarr", tmp_path / "second.zarr"

    run(writer, first, "application/x-zarr")
    writer.write("det_median", np.ones((4, 4), np.uint16))
    writer(
        "stop",
        {"uid": "stop-1", "run_start": "run-1", "time": 2.0, "exit_status": "success"},
    )
    run(writer, second, "application/x-zarr")
    writer.write("det_median", np.ones((4, 4), np.uint16))
    writer(
        "stop",
        {"uid": "stop-2", "run_start": "run-1", "time": 2.0, "exit_status": "success"},
    )

    assert shape_of(first / "det_median") == [1, 4, 4]
    assert shape_of(second / "det_median") == [1, 4, 4]


def test_shutdown_mid_run_leaves_the_store_readable(plain_store: Path) -> None:
    writer = Writer()
    writer.derive("det_filtered", source="det")
    run(writer, plain_store, "application/x-zarr")
    writer.append("det_filtered", np.ones((2, 4, 4), np.uint16))

    writer.shutdown()

    assert shape_of(plain_store / "det_filtered") == [2, 4, 4]
    assert attributes(plain_store / "det_filtered")["redsun"]["run_start"] == "run-1"


def test_an_unknown_mimetype_is_logged_and_the_product_skipped(
    plain_store: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A store no writer knows loses the product, once and audibly, not the run."""
    writer = Writer()
    writer.derive("det_filtered", source="det")
    run(writer, plain_store, "image/tiff")

    with caplog.at_level(logging.WARNING, logger="redsun"):
        writer.append("det_filtered", np.ones((4, 4), np.uint16))
        writer.append("det_filtered", np.ones((4, 4), np.uint16))
    writer.close()

    assert [record.getMessage() for record in caplog.records] == [
        f"'det_filtered' is not written: no writer for 'image/tiff' at {plain_store.as_uri()}."
    ]
    assert not (plain_store / "det_filtered").exists()


def test_a_nested_run_writes_into_the_store_the_run_around_it_named(
    plain_store: Path,
) -> None:
    """A product computed at a nested run's stop lands in the outer run's store."""
    writer = Writer()
    writer.derive("det_median", source="det")
    run(writer, plain_store, "application/x-zarr")
    writer("start", {"uid": "run-2", "time": 1.0})
    writer("event", {"uid": "ev-1", "descriptor": "desc-2", "time": 1.0, "data": {}})

    product = writer.write("det_median", np.ones((4, 4), np.uint16))
    writer(
        "stop",
        {"uid": "stop-2", "run_start": "run-2", "time": 2.0, "exit_status": "success"},
    )
    assert not (plain_store / "det_median" / "zarr.json").exists()
    writer(
        "stop",
        {"uid": "stop-1", "run_start": "run-1", "time": 3.0, "exit_status": "success"},
    )

    assert product == plain_store.as_uri()
    assert attributes(plain_store / "det_median")["redsun"]["run_start"] == "run-1"


def test_a_second_store_for_a_source_leaves_the_first_stream_open(
    tmp_path: Path,
) -> None:
    """A stream closes at its run's stop, so a run naming two stores holds both open."""
    writer = Writer()
    writer.derive("det_filtered", source="det")
    first, second = tmp_path / "first.zarr", tmp_path / "second.zarr"

    run(writer, first, "application/x-zarr")
    writer.append("det_filtered", np.ones((4, 4), np.uint16))
    run(writer, second, "application/x-zarr", start=False)
    writer.append("det_filtered", np.ones((4, 4), np.uint16))

    assert not (first / "det_filtered" / "zarr.json").exists()
    writer(
        "stop",
        {"uid": "stop-1", "run_start": "run-1", "time": 1.0, "exit_status": "success"},
    )
    assert shape_of(first / "det_filtered") == [1, 4, 4]
    assert shape_of(second / "det_filtered") == [1, 4, 4]
