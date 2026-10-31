"""The box layout both sides of the sharedbox transport derive from a description."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

import numpy as np
import pytest
from sharedbox import SharedBox

from redsun.services._layout import (
    ControllerDescription,
    DatatypeDescription,
    box_class,
    box_name,
    index_name,
    namespace,
    pad,
    stream_name,
)

if TYPE_CHECKING:
    from numpy.typing import ArrayLike


def describe(
    datatype: DatatypeDescription,
    access: Literal["r", "w", "rw"] = "rw",
    name: str = "x",
) -> ControllerDescription:
    return {
        "path": ["ctrl"],
        "box": "ctrl-box",
        "attributes": {
            name: {"access": access, "datatype": datatype, "description": ""}
        },
        "commands": ["go"],
        "children": {},
    }


@pytest.fixture
def unique_name() -> str:
    return f"layout-{uuid4().hex[:8]}"


@pytest.fixture
def made(unique_name: str) -> Iterator[list[SharedBox]]:
    boxes: list[SharedBox] = []
    yield boxes
    for box in boxes:
        box.close()
    for name in {box.name for box in boxes}:
        SharedBox.unlink(name)


def test_the_same_description_gives_the_same_box_class(
    unique_name: str, made: list[SharedBox]
) -> None:
    """Attach, with a second call's class, to a box created from the first's."""
    description = describe({"kind": "int"})
    created = box_class(description).create(unique_name)
    made.append(created)
    attached = box_class(description).attach(unique_name)
    made.append(attached)

    created.update(x__value=5)

    assert attached.x__value == 5  # type: ignore[attr-defined]


@pytest.mark.parametrize("prefix", ["A:B:", "A:B"])
def test_a_trailing_colon_is_stripped(prefix: str) -> None:
    """Give the same index name with or without the trailing colon."""
    assert index_name(prefix) == "A:B:fastcs:index"


@pytest.mark.parametrize(
    ("build", "text"),
    [
        (lambda: namespace("MY APP:DET"), "MY APP"),
        (lambda: stream_name("A", "fastcs"), "fastcs"),
        (lambda: stream_name("A", "a.b"), "a.b"),
        (lambda: box_class(describe({"kind": "int"}, name="x__y")), "x__y"),
    ],
)
def test_names_sharedbox_cannot_hold_are_refused(build: Any, text: str) -> None:
    """Raise a ValueError naming the offending text."""
    with pytest.raises(ValueError, match=text):
        build()


def check_uint(box: Any) -> None:
    box.x__value = np.array([2**64 - 1], dtype="uint64")
    assert int(box.x__value[0]) == 2**64 - 1


def check_int(box: Any) -> None:
    with pytest.raises(OverflowError):
        box.x__value = 2**63


def check_str(box: Any) -> None:
    box.x__value = "a" * 1024
    with pytest.raises(ValueError):
        box.x__value = "a" * 1025


def check_enum(box: Any) -> None:
    box.x__setpoint = 1
    assert box.x__setpoint == 1


def check_waveform(box: Any) -> None:
    assert box.x__value.shape == (4, 2)
    assert box.x__shape == (0, 0)
    assert box.x__setpoint_shape == (0, 0)


@pytest.mark.parametrize(
    ("datatype", "check"),
    [
        ({"kind": "uint"}, check_uint),
        ({"kind": "int"}, check_int),
        ({"kind": "str", "capacity": 1024}, check_str),
        ({"kind": "enum", "names": ["A", "B"]}, check_enum),
        ({"kind": "waveform", "dtype": "uint8", "shape": [4, 2]}, check_waveform),
    ],
    ids=["uint", "int", "str", "enum", "waveform"],
)
def test_fields_follow_the_datatype_table(
    datatype: DatatypeDescription,
    check: Callable[[Any], None],
    unique_name: str,
    made: list[SharedBox],
) -> None:
    """Give each datatype the field type of the table, and a waveform its shape field."""
    box = box_class(describe(datatype)).create(unique_name)
    made.append(box)

    check(box)


def test_a_controller_without_fields_has_no_box() -> None:
    """Refuse a box class for a controller with no attributes and no commands."""
    description = describe({"kind": "int"})
    description["attributes"] = {}
    description["commands"] = []
    description["box"] = None

    with pytest.raises(ValueError, match="'root:ctrl'"):
        box_class(description)

    description["path"] = []
    with pytest.raises(ValueError, match="'root'"):
        box_class(description)


def test_a_controller_with_too_many_fields_is_refused() -> None:
    """Refuse more than 256 fields, naming the controller and the count."""
    description = describe({"kind": "int"})
    description["attributes"] = {
        f"a{i}": {"access": "r", "datatype": {"kind": "int"}, "description": ""}
        for i in range(300)
    }
    description["commands"] = []

    with pytest.raises(ValueError, match=r"root:ctrl.*300"):
        box_class(description)


def test_box_names_sit_under_root() -> None:
    """Name the root box `<prefix>:fastcs:root` and children below it."""
    assert box_name("A:B:", "1a2b3c", []) == "A:B:fastcs:1a2b3c:root"
    assert box_name("A", "1a2b3c", ["axes", "0"]) == "A:fastcs:1a2b3c:root:axes:0"


def test_a_short_waveform_is_padded_with_zeros() -> None:
    """Put a waveform shorter than its field at the start, zeros after it."""
    padded = pad([[1, 2]], (2, 3), "int32")

    np.testing.assert_array_equal(padded, [[1, 2, 0], [0, 0, 0]])


@pytest.mark.parametrize("value", [[1, 2], [[1, 2, 3, 4]], [[[1]]]])
def test_a_waveform_that_does_not_fit_its_field_is_refused(value: ArrayLike) -> None:
    """Refuse a waveform with fewer or more dimensions than its field, or longer than it."""
    with pytest.raises(ValueError, match="does not fit"):
        pad(value, (2, 3), "int32")
