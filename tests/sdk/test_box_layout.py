"""The box layout both sides of the sharedbox transport derive from a description."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, Literal
from uuid import uuid4

import numpy as np
import pytest
import sharedbox
from sharedbox import SharedBox

from redsun.services._layout import (
    ControllerDescription,
    DatatypeDescription,
    box_class,
    box_name,
    index_name,
    namespace,
    stream_name,
)


def describe(
    datatype: DatatypeDescription,
    access: Literal["r", "w", "rw"] = "rw",
    name: str = "x",
) -> ControllerDescription:
    return {
        "path": ["ctrl"],
        "box": "ctrl-box",
        "attributes": {
            name: {
                "access": access,
                "datatype": datatype,
                "description": "",
                "label": "",
            }
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

    created.x.publish(value=5)  # type: ignore[attr-defined]

    assert attached.x.value == 5  # type: ignore[attr-defined]


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
    ],
)
def test_names_sharedbox_cannot_hold_are_refused(build: Any, text: str) -> None:
    """Raise a ValueError naming the offending text."""
    with pytest.raises(ValueError, match=text):
        build()


def check_uint(box: Any) -> None:
    box.x.publish(value=np.uint64(2**64 - 1))
    assert int(box.x.read()["value"]) == 2**64 - 1


def check_int(box: Any) -> None:
    with pytest.raises(OverflowError):
        box.x.publish(value=2**63)


def check_str(box: Any) -> None:
    box.x.publish(value="a" * 1024)
    assert box.x.value == "a" * 1024
    with pytest.raises(ValueError):
        box.x.publish(value="a" * 1025)


def check_enum(box: Any) -> None:
    box.x.publish(value=1)
    assert box.x.value == 1


def check_waveform(box: Any) -> None:
    box.x.publish(value=np.ones((3, 2), dtype="uint8"))
    assert box.x.value.shape == (3, 2)
    with pytest.raises(ValueError):
        box.x.publish(value=np.ones((5, 2), dtype="uint8"))


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
    """Give each datatype the field type of the table, and refuse a value it cannot hold."""
    box = box_class(describe(datatype)).create(unique_name)
    made.append(box)

    check(box)


def test_each_attribute_is_one_field_named_after_it(
    unique_name: str, made: list[SharedBox]
) -> None:
    """Give a controller one field per attribute and command, a Setting where writable."""
    description = describe({"kind": "int"}, access="r", name="x")
    for name, access in (("y", "rw"), ("z", "w")):
        description["attributes"][name] = {
            "access": access,  # type: ignore[typeddict-item]
            "datatype": {"kind": "int"},
            "description": "",
            "label": "",
        }
    cls = box_class(description)
    box: Any = cls.create(unique_name)
    made.append(box)

    assert set(cls.__annotations__) == {"x", "y", "z", "go"}
    assert isinstance(box.y, sharedbox.Setting)
    assert isinstance(box.z, sharedbox.Setting)
    assert not isinstance(box.x, sharedbox.Setting)
    assert not isinstance(box.go, sharedbox.Setting)


def test_an_attribute_named_like_a_box_method_gets_a_field_of_its_own(
    unique_name: str, made: list[SharedBox]
) -> None:
    """Add a trailing underscore to the field of an attribute named like a SharedBox method."""
    description = describe({"kind": "int"}, name="name")
    description["attributes"]["close"] = {
        "access": "rw",
        "datatype": {"kind": "int"},
        "description": "",
        "label": "",
    }
    cls = box_class(description)
    box: Any = cls.create(unique_name)
    made.append(box)

    assert set(cls.__annotations__) == {"name_", "close_", "go"}
    box.name_.publish(value=3)
    assert box.name_.value == 3


def test_two_attributes_mapping_to_one_field_are_refused() -> None:
    """Refuse a controller whose `name` and `name_` attributes share the field `name_`."""
    description = describe({"kind": "int"}, name="name")
    description["attributes"]["name_"] = {
        "access": "rw",
        "datatype": {"kind": "int"},
        "description": "",
        "label": "",
    }

    with pytest.raises(ValueError, match=r"root:ctrl.*'name_'"):
        box_class(description)


def test_an_attribute_name_with_double_underscore_is_accepted(
    unique_name: str, made: list[SharedBox]
) -> None:
    """Create a box for an attribute named with a double underscore."""
    box: Any = box_class(describe({"kind": "int"}, name="a__b")).create(unique_name)
    made.append(box)

    box.a__b.publish(value=3)

    assert box.a__b.value == 3


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
    """Refuse more than 256 attributes and commands, naming the controller and the count."""
    description = describe({"kind": "int"})
    description["attributes"] = {
        f"a{i}": {
            "access": "r",
            "datatype": {"kind": "int"},
            "description": "",
            "label": "",
        }
        for i in range(257)
    }
    description["commands"] = []

    with pytest.raises(ValueError, match=r"root:ctrl.*257"):
        box_class(description)


def test_box_names_sit_under_root() -> None:
    """Name the root box `<prefix>:fastcs:root` and children below it."""
    assert box_name("A:B:", "1a2b3c", []) == "A:B:fastcs:1a2b3c:root"
    assert box_name("A", "1a2b3c", ["axes", "0"]) == "A:fastcs:1a2b3c:root:axes:0"
