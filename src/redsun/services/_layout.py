from __future__ import annotations

import re
from typing import TYPE_CHECKING, Annotated, Final, Literal, TypedDict

import numpy as np
from sharedbox import Capacity, DType, Shape, SharedBox

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "DESCRIPTION_CAPACITY",
    "ERROR_CAPACITY",
    "IDENTITY",
    "RESERVED",
    "STRING_CAPACITY",
    "AttributeDescription",
    "ControllerDescription",
    "DatatypeDescription",
    "box_class",
    "box_name",
    "index_class",
    "index_name",
    "namespace",
    "stream_name",
]

RESERVED: Final = "fastcs"
"""The name part under which a service publishes its controller boxes."""

ERROR_CAPACITY: Final = 256
"""Bytes of an `x__error` field."""

STRING_CAPACITY: Final = 256
"""Bytes of a string attribute that gives no capacity."""

DESCRIPTION_CAPACITY: Final = 262_144
"""Bytes of the controller description in the index box."""

IDENTITY: Final = "redsun.services.sharedbox"
"""Schema identity both sides give every box class, so equal layouts match."""

MAX_FIELDS: Final = 256
"""Most fields sharedbox allows in one box."""

MAX_NAME: Final = 240
"""Most characters sharedbox allows in a box name."""

PART: Final = re.compile(r"[A-Za-z0-9_-]+")
"""One part of a box name."""

NAME: Final = re.compile(r"[A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)*")
"""A box name: parts joined by colons."""


class DatatypeDescription(TypedDict, total=False):
    """The datatype of an attribute, as the service describes it."""

    kind: Literal["int", "uint", "float", "bool", "str", "enum", "waveform"]
    units: str
    min: float
    max: float
    min_alarm: float
    max_alarm: float
    precision: int
    capacity: int
    names: list[str]
    dtype: str
    shape: list[int]


class AttributeDescription(TypedDict):
    """One attribute of a controller."""

    access: Literal["r", "w", "rw"]
    datatype: DatatypeDescription
    description: str


class ControllerDescription(TypedDict):
    """A controller and its children, as the index box carries them."""

    path: list[str]
    box: str | None
    """Name of the controller's box, or None for a controller with no attributes or commands."""

    attributes: dict[str, AttributeDescription]
    commands: list[str]
    children: dict[str, ControllerDescription]


def index_class() -> type[SharedBox]:
    """Return a new class of the index box, the box a service publishes first.

    The box holds the service's description in its `description` field,
    versioned by its `version` field.
    """

    # a new class on each call, freed with the boxes made from it: a class
    # held by the module may still be alive when nanobind checks for leaks
    # at exit, which it then reports
    class ServiceIndex(SharedBox, identity=IDENTITY + ".index", kw_only=True):
        version: int = 0
        description: Annotated[bytes, Capacity(DESCRIPTION_CAPACITY)] = b""

    return ServiceIndex


def check_name(name: str) -> str:
    """Return `name` if sharedbox accepts it as a box name, else raise `ValueError`."""
    if len(name) > MAX_NAME or not NAME.fullmatch(name):
        raise ValueError(
            f"box names are parts of [A-Za-z0-9_-] joined by ':', "
            f"at most {MAX_NAME} characters; got {name!r}"
        )
    return name


def namespace(prefix: str) -> str:
    """Return `prefix` without one trailing colon, checked as a box name."""
    return check_name(prefix.removesuffix(":"))


def index_name(prefix: str) -> str:
    """Return the name of the service's index box."""
    return f"{namespace(prefix)}:{RESERVED}:index"


def box_name(prefix: str, run: str, path: Sequence[str]) -> str:
    """Return the name of the box of the controller at `path` below the root, in run `run`."""
    return check_name(":".join((namespace(prefix), RESERVED, run, "root", *path)))


def stream_name(prefix: str, part: str) -> str:
    """Return the name of a stream the service publishes outside the controller boxes.

    Raises
    ------
    ValueError
        If `part` is `fastcs`, which the controller boxes use, or holds a
        character other than a letter, a digit, `_` or `-`.
    """
    if part == RESERVED or not PART.fullmatch(part):
        raise ValueError(f"invalid stream name part {part!r}")
    return check_name(f"{namespace(prefix)}:{part}")


def datatype_field(datatype: DatatypeDescription) -> tuple[object, object]:
    """Return the annotation and the default of a field holding `datatype`."""
    match datatype["kind"]:
        case "int":
            return int, 0
        case "uint":
            return Annotated[np.ndarray, Shape((1,)), DType("uint64")], np.zeros(
                1, dtype="uint64"
            )
        case "float":
            return float, 0.0
        case "bool":
            return bool, False
        case "str":
            return Annotated[
                str, Capacity(datatype.get("capacity", STRING_CAPACITY))
            ], ""
        case "enum":
            return int, 0
        case "waveform":
            shape = datatype["shape"]
            dtype = datatype["dtype"]
            return (
                Annotated[np.ndarray, Shape(tuple(shape)), DType(dtype)],
                np.zeros(shape, dtype=dtype),
            )


def box_class(controller: ControllerDescription) -> type[SharedBox]:
    """Return the box class of one controller, equal for equal descriptions."""
    if not controller["attributes"] and not controller["commands"]:
        raise ValueError(
            f"controller {':'.join(['root', *controller['path']])!r} has no attributes or commands"
        )
    annotations: dict[str, object] = {}
    body: dict[str, object] = {"__annotations__": annotations}

    def add(name: str, annotation: object, default: object) -> None:
        annotations[name] = annotation
        body[name] = default

    def add_request(stem: str) -> None:
        add(f"{stem}__request", int, 0)
        add(f"{stem}__done", int, 0)
        add(f"{stem}__error", Annotated[str, Capacity(ERROR_CAPACITY)], "")

    for name, attribute in controller["attributes"].items():
        if "__" in name:
            raise ValueError(f"attribute name {name!r} contains '__'")
        annotation, default = datatype_field(attribute["datatype"])
        if "r" in attribute["access"]:
            add(f"{name}__value", annotation, default)
        if "w" in attribute["access"]:
            add(f"{name}__setpoint", annotation, default)
            add_request(name)
        if attribute["datatype"]["kind"] == "waveform":
            ndim = len(attribute["datatype"]["shape"])
            shape_field = Annotated[tuple[int, ...], Capacity(ndim)]
            add(f"{name}__shape", shape_field, (0,) * ndim)
            if "w" in attribute["access"]:
                add(f"{name}__setpoint_shape", shape_field, (0,) * ndim)
    for command in controller["commands"]:
        if "__" in command:
            raise ValueError(f"command name {command!r} contains '__'")
        add_request(command)

    if len(annotations) > MAX_FIELDS:
        raise ValueError(
            f"controller {':'.join(['root', *controller['path']])!r} has {len(annotations)} fields; "
            f"a box holds at most {MAX_FIELDS}"
        )
    return type(
        "ControllerBox",
        (SharedBox,),
        body,
        identity=IDENTITY,
        kw_only=True,
    )
