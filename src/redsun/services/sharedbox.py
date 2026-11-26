from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, Literal, TypeVar

import numpy as np
from fastcs.attributes import AttributeIORefT, AttrR, AttrRW, AttrW
from fastcs.datatypes import (
    Bool,
    DType_T,
    Enum,
    Float,
    Int,
    String,
    Table,
    Waveform,
)
from fastcs.transports import Transport
from sharedbox import (
    KindMismatchError,
    SchemaMismatchError,
    SegmentExistsError,
    SegmentNotFoundError,
    Setting,
    SharedBox,
)

from redsun.log import logger

from ._layout import (
    DESCRIPTION_CAPACITY,
    STRING_CAPACITY,
    AttributeDescription,
    ControllerDescription,
    DatatypeDescription,
    NumberDescription,
    ServiceIndex,
    box_class,
    box_name,
    field_name,
    index_name,
    walk,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastcs.controllers import ControllerAPI
    from fastcs.datatypes import DataType

__all__ = ["BoxTransport", "LabelledAttrR", "LabelledAttrRW", "LabelledAttrW"]

_INT64_MAX = 2**63 - 1

_NUMERIC_KEYS: tuple[Literal["units", "min", "max", "min_alarm", "max_alarm"], ...] = (
    "units",
    "min",
    "max",
    "min_alarm",
    "max_alarm",
)
"""Settings of a FastCS `Int` or `Float` the description carries when set."""

_BoxT = TypeVar("_BoxT", bound=SharedBox)


class _Labelled:
    """An attribute that carries a label."""

    label: str


class LabelledAttrR(AttrR[DType_T, AttributeIORefT], _Labelled):
    """A FastCS `AttrR` with a label, the name a client shows for it.

    `BoxTransport` serves the label beside the attribute's description.
    """

    def __init__(
        self,
        datatype: DataType[DType_T],
        io_ref: AttributeIORefT | None = None,
        group: str | None = None,
        initial_value: DType_T | None = None,
        description: str | None = None,
        *,
        label: str,
    ) -> None:
        super().__init__(datatype, io_ref, group, initial_value, description)
        self.label = label


class LabelledAttrW(AttrW[DType_T, AttributeIORefT], _Labelled):
    """A FastCS `AttrW` with a label, the name a client shows for it.

    `BoxTransport` serves the label beside the attribute's description.
    """

    def __init__(
        self,
        datatype: DataType[DType_T],
        io_ref: AttributeIORefT | None = None,
        group: str | None = None,
        description: str | None = None,
        *,
        label: str,
    ) -> None:
        super().__init__(datatype, io_ref, group, description)
        self.label = label


class LabelledAttrRW(AttrRW[DType_T, AttributeIORefT], _Labelled):
    """A FastCS `AttrRW` with a label, the name a client shows for it.

    `BoxTransport` serves the label beside the attribute's description.
    """

    def __init__(
        self,
        datatype: DataType[DType_T],
        io_ref: AttributeIORefT | None = None,
        group: str | None = None,
        initial_value: DType_T | None = None,
        description: str | None = None,
        *,
        label: str,
    ) -> None:
        super().__init__(datatype, io_ref, group, initial_value, description)
        self.label = label


def _cut(text: str, capacity: int, field: str) -> str:
    """Return `text` cut to at most `capacity` UTF-8 bytes, on a character boundary.

    A cut is logged as a warning naming `field`.
    """
    encoded = text.encode()
    if len(encoded) <= capacity:
        return text
    logger.warning(
        f"{field!r} holds {capacity} bytes, so a value of {len(encoded)} bytes was cut"
    )
    return encoded[:capacity].decode(errors="ignore")


def _is_unsigned(datatype: Int) -> bool:
    """Whether `datatype` holds values that do not fit a signed 64-bit integer."""
    return (
        datatype.min is not None
        and datatype.min >= 0
        and datatype.max is not None
        and datatype.max > _INT64_MAX
    )


def _describe_datatype(datatype: DataType[DType_T], where: str) -> DatatypeDescription:
    """Return the description of a FastCS datatype, or raise `ValueError` for a table."""
    match datatype:
        case Table():
            raise ValueError(
                f"attribute {where!r} is a table, which sharedbox cannot carry"
            )
        case Bool():
            return {"kind": "bool"}
        case String():
            return {"kind": "str", "capacity": datatype.length or STRING_CAPACITY}
        case Enum():
            return {"kind": "enum", "names": datatype.names}
        case Waveform():
            return {
                "kind": "waveform",
                "dtype": np.dtype(datatype.array_dtype).name,
                "shape": list(datatype.shape),
            }
        case Int() | Float():
            description: NumberDescription = {
                "kind": "float" if isinstance(datatype, Float) else "int"
            }
            if isinstance(datatype, Int) and _is_unsigned(datatype):
                description["kind"] = "uint"
            if isinstance(datatype, Float):
                description["precision"] = datatype.prec
            for key in _NUMERIC_KEYS:
                if (setting := getattr(datatype, key)) is not None:
                    description[key] = setting
            return description
    raise ValueError(f"attribute {where!r} has unsupported datatype {datatype!r}")


def _to_box(name: str, datatype: DataType[DType_T], value: DType_T) -> object:
    """Return `value` of the attribute `name` as its box field holds it."""
    match datatype:
        case Enum():
            return datatype.index_of(value)
        case Int() if _is_unsigned(datatype):
            return np.uint64(value)
        case String():
            return _cut(value, datatype.length or STRING_CAPACITY, name)
    return value


def _from_box(datatype: DataType[DType_T], raw: Any) -> DType_T:
    """Return `raw`, as the box field of an attribute holds it, as a FastCS value."""
    match datatype:
        case Enum():
            return datatype.members[raw]
        case Int() if _is_unsigned(datatype):
            return int(raw)
    return raw


def _put_handler(
    field: Setting[Any], attribute: AttrW[Any]
) -> Callable[[object], Awaitable[object]]:
    """Return the handler of the requests of `field`, which put them to `attribute`."""

    async def put(raw: object) -> object:
        field.publish(setpoint=raw)
        await attribute.put(_from_box(attribute.datatype, raw), sync_setpoint=True)
        if not isinstance(attribute, AttrR):
            field.publish(value=raw)
        return raw

    return put


def _command_handler(
    command: Callable[[], Awaitable[object]],
) -> Callable[[], Awaitable[None]]:
    """Return the handler of the requests of a command field, which run `command`."""

    async def run() -> None:
        await command()

    return run


@dataclass
class BoxTransport(Transport):
    """Serve a FastCS controller as `sharedbox` boxes, one per controller."""

    def __post_init__(self) -> None:
        """Start with no boxes."""
        self._nodes: list[tuple[ControllerAPI, ControllerDescription]] = []
        self._boxes: dict[str, SharedBox] = {}
        self._index: SharedBox | None = None
        self._prefix = ""
        self._run = ""
        self._published = asyncio.Event()

    def connect(
        self,
        controller_apis: list[ControllerAPI],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Describe the controller tree and publish its boxes, then the index."""
        if len(controller_apis) != 1:
            raise ValueError(
                f"the sharedbox transport serves one controller, got {len(controller_apis)}"
            )
        api = controller_apis[0]
        self._prefix = api.path[0]
        self._nodes = []
        self._run = secrets.token_hex(3)
        root = self._describe(api)
        description = json.dumps(root).encode()
        if len(description) > DESCRIPTION_CAPACITY:
            raise ValueError(
                f"the controller description takes {len(description)} bytes; "
                f"the index holds at most {DESCRIPTION_CAPACITY}"
            )
        self._clean_leftovers()
        try:
            for node_api, node in self._nodes:
                if node["box"] is not None:
                    box = self._publish(box_class(node), node["box"])
                    self._boxes[node["box"]] = box
                    self._publish_initial(box, node_api)
            self._index = self._publish(
                ServiceIndex,
                index_name(self._prefix),
                version=1,
                description=description,
            )
            self._published.set()
        except BaseException:
            self._close()
            raise

    def _describe(self, api: ControllerAPI) -> ControllerDescription:
        """Return the description of `api` and its sub-APIs, recording each pair."""
        path = list(api.path[1:])
        attributes: dict[str, AttributeDescription] = {
            name: {
                "access": attribute.access_mode,
                "datatype": _describe_datatype(
                    attribute.datatype, "/".join((*api.path, name))
                ),
                "description": attribute.description or "",
                "label": attribute.label if isinstance(attribute, _Labelled) else "",
            }
            for name, attribute in api.attributes.items()
        }
        commands = list(api.command_methods)
        description: ControllerDescription = {
            "path": path,
            "box": box_name(self._prefix, self._run, path)
            if attributes or commands
            else None,
            "attributes": attributes,
            "commands": commands,
            "children": {},
        }
        description["children"] = {
            key: self._describe(sub) for key, sub in api.sub_apis.items()
        }
        self._nodes.append((api, description))
        return description

    def _clean_leftovers(self) -> None:
        """Unlink the boxes and the index a previous run of this service left."""
        name = index_name(self._prefix)
        try:
            old = ServiceIndex.attach(name)
        except SegmentNotFoundError:
            return
        except (SchemaMismatchError, KindMismatchError):
            ServiceIndex.unlink(name)
            return
        try:
            for node in walk(json.loads(old.description)):
                if node["box"] is not None:
                    with contextlib.suppress(SegmentNotFoundError):
                        SharedBox.unlink(node["box"])
        finally:
            old.unlink()
            old.close()

    def _publish(self, cls: type[_BoxT], name: str, **values: object) -> _BoxT:
        """Create the box `name`, replacing one a stopped service left behind."""
        try:
            return cls.create(name, **values)
        except SegmentExistsError:
            cls.unlink(name)
            return cls.create(name, **values)

    @staticmethod
    def _publish_initial(box: SharedBox, api: ControllerAPI) -> None:
        """Publish the current value of each readable attribute, and its setpoint if writable."""
        for name, attribute in api.attributes.items():
            if isinstance(attribute, AttrR):
                value = _to_box(name, attribute.datatype, attribute.get())
                field = getattr(box, field_name(name))
                if isinstance(attribute, AttrW):
                    field.publish(value=value, setpoint=value)
                else:
                    field.publish(value=value)

    async def serve(self) -> None:
        """Mirror attribute updates into the boxes and answer requests until cancelled."""
        try:
            for api, node in self._nodes:
                if node["box"] is not None:
                    await self._serve_box(api, self._boxes[node["box"]])
            await asyncio.Event().wait()
        finally:
            self._close()

    async def _serve_box(self, api: ControllerAPI, box: SharedBox) -> None:
        """Mirror the attributes of `api` into `box`, and answer its requests.

        The servers run until the box closes.
        """
        for name, attribute in api.attributes.items():
            if isinstance(attribute, AttrR):
                callback = partial(self._update, box, name, attribute.datatype)
                attribute.add_on_update_callback(callback)
                await callback(attribute.get())
            if isinstance(attribute, AttrW):
                field = getattr(box, field_name(name))
                field.serve(_put_handler(field, attribute))
        for name, command in api.command_methods.items():
            getattr(box, field_name(name)).serve(_command_handler(command))

    async def reachable(self) -> None:
        """Return once the index is published."""
        await self._published.wait()

    async def _update(
        self, box: SharedBox, name: str, datatype: DataType[DType_T], value: DType_T
    ) -> None:
        """Write the value of the attribute `name` to its box."""
        if box.closed:
            return
        try:
            getattr(box, field_name(name)).publish(value=_to_box(name, datatype, value))
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(
                f"attribute {name!r} cannot be written to its box: {exc}"
            ) from exc

    def _close(self) -> None:
        """Close and unlink every box and the index."""
        for box in (*self._boxes.values(), self._index):
            if box is not None:
                box.unlink()
                box.close()
        self._boxes.clear()
        self._index = None
