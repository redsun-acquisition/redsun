from __future__ import annotations

import re
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Final,
    Literal,
    NamedTuple,
    Required,
    TypeAlias,
    TypedDict,
)

import numpy as np
from sharedbox import Capacity, DType, Shape, SharedBox

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from numpy.typing import ArrayLike, DTypeLike, NDArray

__all__ = [
    "DESCRIPTION_CAPACITY",
    "ERROR_CAPACITY",
    "IDENTITY",
    "RESERVED",
    "STRING_CAPACITY",
    "AttributeDescription",
    "ControllerDescription",
    "DatatypeDescription",
    "Field",
    "NumberDescription",
    "ServiceIndex",
    "box_class",
    "box_name",
    "controller_label",
    "index_name",
    "namespace",
    "pad",
    "stream_name",
    "unpad",
    "walk",
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


class NumberDescription(TypedDict, total=False):
    """An `int`, `uint` or `float` attribute, as the service describes it."""

    kind: Required[Literal["int", "uint", "float"]]
    units: str
    min: float
    max: float
    min_alarm: float
    max_alarm: float
    precision: int


class BoolDescription(TypedDict):
    """A `bool` attribute, as the service describes it."""

    kind: Literal["bool"]


class StrDescription(TypedDict):
    """A `str` attribute, as the service describes it."""

    kind: Literal["str"]
    capacity: int
    """Bytes of the field holding the value."""


class EnumDescription(TypedDict):
    """An `enum` attribute, as the service describes it."""

    kind: Literal["enum"]
    names: list[str]
    """The values of the enum, in the order of their indices."""


class WaveformDescription(TypedDict):
    """A `waveform` attribute, as the service describes it."""

    kind: Literal["waveform"]
    dtype: str
    shape: list[int]
    """The largest shape the waveform takes."""


DatatypeDescription: TypeAlias = (
    NumberDescription
    | BoolDescription
    | StrDescription
    | EnumDescription
    | WaveformDescription
)
"""The datatype of an attribute, as the service describes it."""


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


class ServiceIndex(SharedBox, identity=IDENTITY + ".index", kw_only=True):
    """The index box, the box a service publishes first."""

    version: int = 0
    """Incremented each time the service publishes a new description."""

    description: Annotated[bytes, Capacity(DESCRIPTION_CAPACITY)] = b""
    """The service's controllers, as a JSON `ControllerDescription`."""


def pad(value: ArrayLike, shape: Sequence[int], dtype: DTypeLike) -> NDArray[Any]:
    """Return `value` at the start of a zeroed array of the waveform field's `shape`.

    Raises
    ------
    ValueError
        If `value` has another number of dimensions than `shape`, or is longer
        than `shape` along one of them.
    """
    array = np.asarray(value)
    if array.ndim != len(shape) or any(
        size > limit for size, limit in zip(array.shape, shape, strict=True)
    ):
        raise ValueError(
            f"a waveform of shape {array.shape} does not fit the field's {tuple(shape)}"
        )
    padded = np.zeros(shape, dtype=dtype)
    padded[tuple(slice(0, size) for size in array.shape)] = array
    return padded


def unpad(raw: NDArray[Any], shape: Sequence[int]) -> NDArray[Any]:
    """Return the start of the waveform field `raw` that `shape` covers, as a copy."""
    return np.array(raw[tuple(slice(0, size) for size in shape)])


def walk(description: ControllerDescription) -> Iterator[ControllerDescription]:
    """Yield `description` and every controller below it, parents first."""
    yield description
    for child in description["children"].values():
        yield from walk(child)


def controller_label(description: ControllerDescription) -> str:
    """Return the controller's path from the root, joined by colons, for messages."""
    return ":".join(["root", *description["path"]])


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


class Field(NamedTuple):
    """The annotation and the default of a box field."""

    annotation: object
    default: object


def datatype_field(datatype: DatatypeDescription) -> Field:
    """Return the field holding `datatype`."""
    match datatype["kind"]:
        case "int" | "enum":
            return Field(int, 0)
        case "uint":
            return Field(
                Annotated[np.ndarray, Shape((1,)), DType("uint64")],
                np.zeros(1, dtype="uint64"),
            )
        case "float":
            return Field(float, 0.0)
        case "bool":
            return Field(bool, False)
        case "str":
            return Field(Annotated[str, Capacity(datatype["capacity"])], "")
        case "waveform":
            shape, dtype = datatype["shape"], datatype["dtype"]
            return Field(
                Annotated[np.ndarray, Shape(tuple(shape)), DType(dtype)],
                np.zeros(shape, dtype=dtype),
            )


def box_class(controller: ControllerDescription) -> type[SharedBox]:
    """Return the box class of one controller, equal for equal descriptions."""
    if not controller["attributes"] and not controller["commands"]:
        raise ValueError(
            f"controller {controller_label(controller)!r} has no attributes or commands"
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
            f"controller {controller_label(controller)!r} has {len(annotations)} fields; "
            f"a box holds at most {MAX_FIELDS}"
        )
    return type(
        "ControllerBox",
        (SharedBox,),
        body,
        identity=IDENTITY,
        kw_only=True,
    )
