from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

import numpy as np
from fastcs.attributes import AttrR, AttrW
from fastcs.datatypes import Bool, Enum, Float, Int, String, Table, Waveform
from fastcs.transports import Transport
from sharedbox import SegmentExistsError, SharedBox

from ._layout import (
    DESCRIPTION_CAPACITY,
    ERROR_CAPACITY,
    STRING_CAPACITY,
    ControllerDescription,
    DatatypeDescription,
    ServiceIndex,
    box_class,
    box_name,
    index_name,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastcs.controllers import ControllerAPI

__all__ = ["BoxTransport"]

INT64_MAX = 2**63 - 1


def cut(text: str, capacity: int) -> str:
    """Return `text` cut to at most `capacity` UTF-8 bytes, on a character boundary."""
    return text.encode()[:capacity].decode(errors="ignore")


def is_unsigned(datatype: Int) -> bool:
    """Whether `datatype` holds values that do not fit a signed 64-bit integer."""
    return (
        datatype.min is not None
        and datatype.min >= 0
        and datatype.max is not None
        and datatype.max > INT64_MAX
    )


def describe_datatype(datatype: Any, where: str) -> DatatypeDescription:
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
            description: dict[str, Any] = {
                "kind": "float" if isinstance(datatype, Float) else "int"
            }
            if isinstance(datatype, Int) and is_unsigned(datatype):
                description["kind"] = "uint"
            if isinstance(datatype, Float):
                description["precision"] = datatype.prec
            for key in ("units", "min", "max", "min_alarm", "max_alarm"):
                if getattr(datatype, key) is not None:
                    description[key] = getattr(datatype, key)
            return description  # type: ignore[return-value]
    raise ValueError(f"attribute {where!r} has unsupported datatype {datatype!r}")


def to_box(datatype: Any, value: Any) -> dict[str, Any]:
    """Return the box fields (without the attribute name) holding `value`."""
    match datatype:
        case Enum():
            return {"": datatype.index_of(value)}
        case Int() if is_unsigned(datatype):
            return {"": np.array([value], dtype="uint64")}
        case String():
            return {"": cut(value, datatype.length or STRING_CAPACITY)}
        case Waveform():
            padded = np.zeros(datatype.shape, dtype=datatype.array_dtype)
            padded[tuple(slice(0, size) for size in value.shape)] = value
            return {"": padded, "shape": tuple(value.shape)}
    return {"": value}


def from_box(datatype: Any, raw: Any) -> Any:
    """Return the FastCS value of a setpoint read from a box."""
    match datatype:
        case Enum():
            return datatype.members[raw]
        case Int() if is_unsigned(datatype):
            return int(raw[0])
        case Waveform():
            return np.array(raw)
    return raw


@dataclass
class BoxTransport(Transport):
    """Serve a FastCS controller as `sharedbox` boxes, one per controller."""

    def __post_init__(self) -> None:
        """Start with no boxes."""
        self._nodes: list[tuple[ControllerAPI, ControllerDescription]] = []
        self._boxes: dict[str, SharedBox] = {}
        self._index: ServiceIndex | None = None
        self._prefix = ""

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
        root = self._describe(api)
        description = json.dumps(root).encode()
        if len(description) > DESCRIPTION_CAPACITY:
            raise ValueError(
                f"the controller description takes {len(description)} bytes; "
                f"the index holds at most {DESCRIPTION_CAPACITY}"
            )
        try:
            for node_api, node in self._nodes:
                if node["box"] is not None:
                    self._boxes[node["box"]] = self._publish(
                        box_class(node), node["box"], self._initial_values(node_api)
                    )
            self._index = self._publish(
                ServiceIndex,
                index_name(self._prefix),
                {"version": 1, "description": description},
            )
        except BaseException:
            self._close()
            raise

    def _describe(self, api: ControllerAPI) -> ControllerDescription:
        """Return the description of `api` and its sub-APIs, recording each pair."""
        path = list(api.path)
        attributes = {
            name: {
                "access": attribute.access_mode,
                "datatype": describe_datatype(
                    attribute.datatype, "/".join((*path, name))
                ),
                "description": attribute.description or "",
            }
            for name, attribute in api.attributes.items()
        }
        commands = list(api.command_methods)
        description: ControllerDescription = {
            "path": path,
            "box": box_name(self._prefix, path) if attributes or commands else None,
            "attributes": attributes,  # type: ignore[typeddict-item]
            "commands": commands,
            "children": {},
        }
        description["children"] = {
            key: self._describe(sub) for key, sub in api.sub_apis.items()
        }
        self._nodes.append((api, description))
        return description

    def _publish(self, cls: type[SharedBox], name: str, values: dict[str, Any]) -> Any:
        """Create the box `name`, replacing one a stopped service left behind."""
        try:
            return cls.create(name, **values)
        except SegmentExistsError:
            cls.unlink(name)
            return cls.create(name, **values)

    def _initial_values(self, api: ControllerAPI) -> dict[str, Any]:
        """Return the box fields holding the current value of each readable attribute."""
        values: dict[str, Any] = {}
        for name, attribute in api.attributes.items():
            if isinstance(attribute, AttrR):
                values.update(self._fields(name, attribute.datatype, attribute.get()))
        return values

    @staticmethod
    def _fields(name: str, datatype: Any, value: Any) -> dict[str, Any]:
        """Return the box fields holding the value of the attribute `name`."""
        return {
            f"{name}__{key or 'value'}": field
            for key, field in to_box(datatype, value).items()
        }

    async def serve(self) -> None:
        """Mirror attribute updates into the boxes and answer requests until cancelled."""
        try:
            async with asyncio.TaskGroup() as group:
                for api, node in self._nodes:
                    if node["box"] is None:
                        continue
                    box = self._boxes[node["box"]]
                    for name, attribute in api.attributes.items():
                        if isinstance(attribute, AttrR):
                            callback = partial(
                                self._update, box, name, attribute.datatype
                            )
                            attribute.add_on_update_callback(callback)
                            await callback(attribute.get())
                        if isinstance(attribute, AttrW):
                            group.create_task(
                                self._answer(
                                    box, name, partial(self._put, box, name, attribute)
                                )
                            )
                    for name, command in api.command_methods.items():
                        group.create_task(self._answer(box, name, command))
                await asyncio.Event().wait()
        finally:
            self._close()

    async def _update(self, box: Any, name: str, datatype: Any, value: Any) -> None:
        """Write the value of the attribute `name` to its box."""
        if not box.closed:
            box.update(**self._fields(name, datatype, value))

    @staticmethod
    async def _put(box: Any, name: str, attribute: Any) -> None:
        """Put the setpoint in the box to the attribute `name`."""
        setpoint = from_box(attribute.datatype, getattr(box, f"{name}__setpoint"))
        await attribute.put(setpoint, sync_setpoint=True)

    @staticmethod
    async def _answer(box: Any, stem: str, run: Callable[[], Awaitable[Any]]) -> None:
        """Run `run` for every request number written to `<stem>__request`.

        A watch skips to the latest write, so after each wake the request
        number is compared with `<stem>__done` and `run` repeats until they
        match.
        """

        async def serve_pending() -> None:
            while (number := getattr(box, f"{stem}__request")) != getattr(
                box, f"{stem}__done"
            ):
                error = ""
                try:
                    await run()
                except Exception as exc:  # noqa: BLE001
                    error = str(exc) or type(exc).__name__
                # One update, so a client woken by `done` never reads the
                # error of the previous request.
                box.update(
                    **{
                        f"{stem}__error": cut(error, ERROR_CAPACITY),
                        f"{stem}__done": number,
                    }
                )

        watch = box.watch(f"{stem}__request")
        await serve_pending()
        async for _ in watch:
            await serve_pending()

    def _close(self) -> None:
        """Close and unlink every box and the index."""
        for box in (*self._boxes.values(), self._index):
            if box is not None:
                box.unlink()
                box.close()
        self._boxes.clear()
        self._index = None
