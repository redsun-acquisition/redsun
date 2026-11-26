from __future__ import annotations

import re
from typing import (
    TYPE_CHECKING,
    Annotated,
    Final,
    Literal,
    Required,
    TypeAlias,
    TypedDict,
)

import numpy as np
from sharedbox import Attr, Capacity, DType, MaxShape, Setting, SharedBox, attr

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

__all__ = [
    "DESCRIPTION_CAPACITY",
    "IDENTITY",
    "RESERVED",
    "STRING_CAPACITY",
    "AttributeDescription",
    "ControllerDescription",
    "DatatypeDescription",
    "NumberDescription",
    "ServiceIndex",
    "box_class",
    "box_name",
    "controller_label",
    "field_name",
    "index_name",
    "namespace",
    "stream_name",
    "value_type",
    "walk",
]

RESERVED: Final = "fastcs"
"""The name part under which a service publishes its controller boxes."""

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

BOX_MEMBERS: Final = frozenset(n for n in dir(SharedBox) if not n.startswith("_"))
"""Public names of a `SharedBox`, which a field cannot take."""

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
    label: str
    """The name a client shows for the attribute, empty when the service gives none."""


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


def value_type(datatype: DatatypeDescription) -> object:
    """Return the type an attribute of `datatype` has in its box."""
    match datatype["kind"]:
        case "int" | "enum":
            return int
        case "uint":
            return np.uint64
        case "float":
            return float
        case "bool":
            return bool
        case "str":
            return Annotated[str, Capacity(datatype["capacity"])]
        case "waveform":
            return Annotated[
                np.ndarray, MaxShape(tuple(datatype["shape"])), DType(datatype["dtype"])
            ]


def field_name(name: str) -> str:
    """Return the box field of the attribute or command `name`.

    A name that `SharedBox` uses for one of its own members gets a trailing
    underscore.
    """
    return f"{name}_" if name in BOX_MEMBERS else name


def box_class(controller: ControllerDescription) -> type[SharedBox]:
    """Return the box class of one controller, equal for equal descriptions.

    Each attribute and each command is one field named after it: an `Attr` for
    a read-only attribute, a `Setting` for a writable one and an `Attr[None]`
    for a command.
    """
    if not controller["attributes"] and not controller["commands"]:
        raise ValueError(
            f"controller {controller_label(controller)!r} has no attributes or commands"
        )
    annotations: dict[str, object] = {}

    def add(name: str, annotation: object) -> None:
        field = field_name(name)
        if field in annotations:
            raise ValueError(
                f"controller {controller_label(controller)!r} has two attributes or "
                f"commands that map to the field {field!r}"
            )
        annotations[field] = annotation

    for name, attribute in controller["attributes"].items():
        kind = value_type(attribute["datatype"])
        add(name, Attr[kind] if attribute["access"] == "r" else Setting[kind])  # type: ignore[valid-type]
    for command in controller["commands"]:
        add(command, Attr[None])

    if len(annotations) > MAX_FIELDS:
        raise ValueError(
            f"controller {controller_label(controller)!r} has {len(annotations)} fields; "
            f"a box holds at most {MAX_FIELDS}"
        )
    return type(
        "ControllerBox",
        (SharedBox,),
        {"__annotations__": annotations, **{name: attr() for name in annotations}},
        identity=IDENTITY,
        kw_only=True,
    )
