"""The box layout both sides of the sharedbox transport derive from a description."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import numpy as np
import pytest
from sharedbox import SharedBox

from redsun.services._layout import (
    ControllerDescription,
    DatatypeDescription,
    box_class,
    index_name,
    namespace,
    stream_name,
)


def describe(
    datatype: DatatypeDescription, access: str = "rw", name: str = "x"
) -> ControllerDescription:
    return {
        "path": ["ctrl"],
        "box": "ignored",
        "attributes": {
            name: {"access": access, "datatype": datatype, "description": ""}  # type: ignore[typeddict-item]
        },
        "commands": ["go"],
        "children": {},
    }


@pytest.fixture
def box_name() -> str:
    return f"layout-{uuid4().hex[:8]}"


@pytest.fixture
def made(box_name: str) -> Iterator[list[SharedBox]]:
    boxes: list[SharedBox] = []
    yield boxes
    for box in boxes:
        box.close()
        box.unlink()


def test_the_same_description_gives_the_same_box_class(
    box_name: str, made: list[SharedBox]
) -> None:
    """Attach, with a second call's class, to a box created from the first's."""
    description = describe({"kind": "int"})
    created = box_class(description).create(box_name)
    made.append(created)
    attached = box_class(description).attach(box_name)
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


def test_fields_follow_the_datatype_table(box_name: str, made: list[SharedBox]) -> None:
    """Give each datatype its field type, and a waveform its shape field."""
    uint = box_class(describe({"kind": "uint"}, "r")).create(f"{box_name}-u")
    made.append(uint)
    uint.x__value = np.array([2**64 - 1], dtype="uint64")  # type: ignore[attr-defined]
    assert int(uint.x__value[0]) == 2**64 - 1  # type: ignore[attr-defined]

    signed = box_class(describe({"kind": "int"}, "r")).create(f"{box_name}-i")
    made.append(signed)
    with pytest.raises(OverflowError):
        signed.x__value = 2**63  # type: ignore[attr-defined]

    text = box_class(describe({"kind": "str", "capacity": 1024})).create(
        f"{box_name}-s"
    )
    made.append(text)
    text.x__value = "a" * 1024  # type: ignore[attr-defined]
    with pytest.raises(ValueError):
        text.x__value = "a" * 1025  # type: ignore[attr-defined]

    enum = box_class(describe({"kind": "enum", "names": ["A", "B"]})).create(
        f"{box_name}-e"
    )
    made.append(enum)
    enum.x__setpoint = 1  # type: ignore[attr-defined]
    assert enum.x__setpoint == 1  # type: ignore[attr-defined]

    wave = box_class(
        describe({"kind": "waveform", "dtype": "uint8", "shape": [4, 2]}, "r")
    ).create(f"{box_name}-w")
    made.append(wave)
    assert wave.x__value.shape == (4, 2)  # type: ignore[attr-defined]
    assert wave.x__shape == (0, 0)  # type: ignore[attr-defined]


def test_a_controller_with_too_many_fields_is_refused() -> None:
    """Refuse more than 256 fields, naming the controller and the count."""
    description = describe({"kind": "int"})
    description["attributes"] = {
        f"a{i}": {"access": "r", "datatype": {"kind": "int"}, "description": ""}
        for i in range(300)
    }
    description["commands"] = []

    with pytest.raises(ValueError, match=r"ctrl.*300"):
        box_class(description)
