from __future__ import annotations

import asyncio
import enum
import json
import time
from typing import TYPE_CHECKING, Any, ClassVar, cast, get_origin

import numpy as np
from bluesky.protocols import Reading
from event_model import Limits, LimitsRange
from ophyd_async.core import (
    NO_ARG_VOID_SIGNATURE,
    CommandBackend,
    Device,
    DeviceConnector,
    DeviceFiller,
    DeviceMock,
    DeviceVector,
    SignalBackend,
    SignalDatatypeT,
    SignalMetadata,
    SignalR,
    SignalRW,
    SignalW,
    StrictEnum,
    TriggerableCommand,
    make_datakey,
)
from sharedbox import BoxClosedError, SegmentNotFoundError

from redsun.aio import cancel_task
from redsun.log import logger

from ..services._layout import (
    AttributeDescription,
    ControllerDescription,
    ServiceIndex,
    box_class,
    controller_label,
    index_name,
    pad,
    stream_name,
    unpad,
    walk,
)

if TYPE_CHECKING:
    import inspect
    from collections.abc import Mapping

    from event_model import DataKey
    from ophyd_async.core import Callback, SignalDatatype
    from sharedbox import FieldWatch, SharedBox

__all__ = [
    "BoxCommandBackend",
    "BoxDeviceConnector",
    "BoxPutError",
    "BoxSignalBackend",
    "stream_name",
]

_ATTACH_RETRY = 0.1
"""Seconds between attempts to attach a service's index."""

_DATATYPES: dict[str, type] = {
    "int": int,
    "uint": int,
    "float": float,
    "bool": bool,
    "str": str,
    "waveform": np.ndarray,
}
"""Python type of each datatype kind a description names, enums apart."""

_SIGNALS = {"r": SignalR, "w": SignalW, "rw": SignalRW}


class BoxPutError(Exception):
    """A service refused a write or a command, or it raised while running it."""

    attribute: str
    """Name of the attribute or command the service refused."""

    def __init__(self, attribute: str, message: str) -> None:
        super().__init__(f"{attribute}: {message}")
        self.attribute = attribute


def _first_difference(
    old: ControllerDescription, new: ControllerDescription, path: str = "root"
) -> str | None:
    """Return the path of the first attribute, command or child that differs, or None."""
    for name in sorted({*old["attributes"], *new["attributes"]}):
        before = old["attributes"].get(name)
        after = new["attributes"].get(name)
        if (before and before["access"], before and before["datatype"]) != (
            after and after["access"],
            after and after["datatype"],
        ):
            return f"{path}/{name}"
    for name in sorted({*old["commands"], *new["commands"]}):
        if (name in old["commands"]) != (name in new["commands"]):
            return f"{path}/{name}"
    for key in sorted({*old["children"], *new["children"]}):
        if key not in old["children"] or key not in new["children"]:
            return f"{path}/{key}"
        if difference := _first_difference(
            old["children"][key], new["children"][key], f"{path}/{key}"
        ):
            return difference
    return None


def _box_key(description: ControllerDescription) -> str:
    """Return the key of the box of `description`, the same across runs of a service."""
    return ":".join(description["path"])


def _attached_name(boxes: Mapping[str, SharedBox], key: str) -> str:
    """Return the name of the box attached under `key`, or `key` before it is attached."""
    box = boxes.get(key)
    return key if box is None else box.name


async def _request(box: SharedBox, stem: str, name: str, **values: Any) -> None:
    """Write `values` and a new request number to `box`, then wait for the answer.

    Raises
    ------
    BoxPutError
        The service answered with an error message.
    """
    number = getattr(box, f"{stem}__request") + 1
    box.update(**values, **{f"{stem}__request": number})
    while True:
        watch = box.watch(f"{stem}__done")
        if getattr(box, f"{stem}__done") >= number:
            break
        await asyncio.wrap_future(watch.future())
    if error := getattr(box, f"{stem}__error"):
        raise BoxPutError(name, error)


class BoxSignalBackend(SignalBackend[SignalDatatypeT]):
    """A signal backed by one attribute of a controller box."""

    def __init__(self, datatype: type[SignalDatatypeT] | None) -> None:
        super().__init__(datatype)
        self._boxes: Mapping[str, SharedBox] = {}
        self._box_key = ""
        self._attribute = ""
        self._description: AttributeDescription
        self._names: list[str] = []
        self._readback = ""
        self._readback_shape = ""
        self._lock = asyncio.Lock()
        self._callback: Callback[Reading[SignalDatatypeT]] | None = None
        self._follower: asyncio.Task[None] | None = None

    def _bind(
        self,
        boxes: Mapping[str, SharedBox],
        box_key: str,
        attribute: str,
        description: AttributeDescription,
    ) -> None:
        """Say which attribute of which box this backend reads and writes."""
        self._boxes = boxes
        self._box_key = box_key
        self._attribute = attribute
        self._description = description
        datatype = description["datatype"]
        self._names = datatype["names"] if datatype["kind"] == "enum" else []
        if "r" in description["access"]:
            self._readback = f"{attribute}__value"
            self._readback_shape = f"{attribute}__shape"
        else:
            self._readback = f"{attribute}__setpoint"
            self._readback_shape = f"{attribute}__setpoint_shape"

    def _box_name(self) -> str:
        """Return the name of the attached box, the key before it is attached."""
        return _attached_name(self._boxes, self._box_key)

    def _box(self) -> SharedBox:
        """Return the attached box of the attribute."""
        return self._boxes[self._box_key]

    def source(self, name: str, read: bool) -> str:
        """Return the location of the attribute."""
        return f"sharedbox://{self._box_name()}/{self._attribute}"

    async def connect(self, timeout: float) -> None:
        """Check the declared datatype against the description.

        Raises
        ------
        TypeError
            The declared datatype is not what the service serves.
        """
        self._check_datatype(self._description["datatype"]["kind"])
        if self._callback:
            self._follow_readback(self._callback)

    def _check_datatype(self, kind: str) -> None:
        """Take the served datatype, or check the declared one against it.

        Raises
        ------
        TypeError
            The declared datatype is not what the service serves.
        """
        if kind == "enum":
            if self.datatype is None:
                self.datatype = StrictEnum(  # type: ignore[call-arg, assignment]
                    self._attribute, {name.upper(): name for name in self._names}
                )
            elif not (
                isinstance(self.datatype, type)
                and issubclass(self.datatype, enum.Enum)
                and {member.value for member in self.datatype} == set(self._names)
            ):
                self._mismatch(f"enum of {self._names}")
            return
        expected = _DATATYPES[kind]
        if self.datatype is None:
            self.datatype = expected
        elif (get_origin(self.datatype) or self.datatype) is not expected:
            self._mismatch(expected.__name__)

    def _mismatch(self, served: str) -> None:
        """Raise the error of a declared datatype the service does not serve."""
        raise TypeError(
            f"{self._box_name()}: {self._attribute} is declared as {self.datatype} "
            f"but the service serves {served}"
        )

    def _read(self, field: str, shape_field: str) -> SignalDatatypeT:
        """Return the value the box field `field` holds, as the signal's datatype.

        A waveform is cut to the shape the field `shape_field` holds.
        """
        box = self._box()
        raw = getattr(box, field)
        value: object = raw
        match self._description["datatype"]["kind"]:
            case "uint":
                value = int(raw[0])
            case "enum":
                value = cast("type[enum.Enum]", self.datatype)(self._names[raw])
            case "waveform":
                value = unpad(raw, getattr(box, shape_field))
        # sharedbox builds the box class at runtime, so no checker sees the
        # field's type; connect checked it against the signal's datatype
        return cast("SignalDatatypeT", value)

    def _setpoint_fields(self, value: SignalDatatypeT) -> dict[str, object]:
        """Return the box fields a write of `value` sets."""
        datatype = self._description["datatype"]
        setpoint = f"{self._attribute}__setpoint"
        match datatype["kind"]:
            case "uint":
                return {setpoint: np.array([value], dtype="uint64")}
            case "enum":
                name = value.value if isinstance(value, enum.Enum) else value
                return {setpoint: self._names.index(str(name))}
            case "waveform":
                array = np.asarray(value)
                return {
                    setpoint: pad(array, datatype["shape"], datatype["dtype"]),
                    f"{setpoint}_shape": array.shape,
                }
        return {setpoint: value}

    def _current(self) -> Reading[SignalDatatypeT]:
        """Return the current value as a reading."""
        return Reading(
            value=self._read(self._readback, self._readback_shape),
            timestamp=time.time(),
            alarm_severity=0,
        )

    async def put(self, value: SignalDatatypeT | None) -> None:
        """Write `value` and wait until the service has put it.

        Raises
        ------
        TypeError
            `value` is None.
        BoxPutError
            The service refused the value or its put raised.
        """
        if value is None:
            raise TypeError(f"{self._attribute}: a put to a box needs a value")
        async with self._lock:
            await _request(
                self._box(),
                self._attribute,
                self._attribute,
                **self._setpoint_fields(value),
            )

    async def get_datakey(self, source: str) -> DataKey:
        """Return the data key, with the units, precision, limits and choices served."""
        datatype = self._description["datatype"]
        metadata = SignalMetadata()
        match datatype["kind"]:
            case "int" | "uint" | "float":
                if "units" in datatype:
                    metadata["units"] = datatype["units"]
                if "precision" in datatype:
                    metadata["precision"] = datatype["precision"]
                limits = Limits()
                if "min" in datatype or "max" in datatype:
                    limits["control"] = LimitsRange(
                        low=datatype.get("min"), high=datatype.get("max")
                    )
                if "min_alarm" in datatype or "max_alarm" in datatype:
                    limits["alarm"] = LimitsRange(
                        low=datatype.get("min_alarm"), high=datatype.get("max_alarm")
                    )
                if limits:
                    metadata["limits"] = limits
            case "enum":
                metadata["choices"] = self._names
        return make_datakey(
            self.datatype,  # type: ignore[arg-type]
            self._current()["value"],
            source,
            metadata,
        )

    async def get_reading(self) -> Reading[SignalDatatypeT]:
        """Return the current value."""
        return self._current()

    async def get_value(self) -> SignalDatatypeT:
        """Return the current value."""
        return self._current()["value"]

    async def get_setpoint(self) -> SignalDatatypeT:
        """Return the last value written."""
        if "w" not in self._description["access"]:
            return await self.get_value()
        return self._read(
            f"{self._attribute}__setpoint", f"{self._attribute}__setpoint_shape"
        )

    def set_callback(self, callback: Callback[Reading[SignalDatatypeT]] | None) -> None:
        """Call `callback` with the current reading, then with each new one."""
        if callback and self._callback:
            raise RuntimeError("Cannot set a callback when one is already set")
        self._callback = callback
        if callback:
            self._follow_readback(callback)
        elif self._follower is not None:
            # ophyd-async unsubscribes on the caller's thread, often the GUI's
            cancel_task(self._follower)
            self._follower = None

    def _follow_readback(self, callback: Callback[Reading[SignalDatatypeT]]) -> None:
        """Call `callback` with the current reading, then follow the box's value."""
        if self._follower is not None:
            cancel_task(self._follower)
        watch = self._box().watch(self._readback)
        callback(self._current())
        self._follower = asyncio.create_task(self._follow(watch, callback))

    async def _follow(
        self, watch: FieldWatch[object], callback: Callback[Reading[SignalDatatypeT]]
    ) -> None:
        """Call `callback` with the reading after each write to the value."""
        try:
            async for _ in watch:
                try:
                    callback(self._current())
                except BoxClosedError:
                    return
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "callback of %s/%s failed", self._box_name(), self._attribute
                    )
        except BoxClosedError:
            return


class BoxCommandBackend(CommandBackend[[], None]):
    """A command backed by the request fields of a controller box."""

    def __init__(self) -> None:
        super().__init__(NO_ARG_VOID_SIGNATURE)
        self._boxes: Mapping[str, SharedBox] = {}
        self._box_key = ""
        self._command = ""
        self._lock = asyncio.Lock()

    def _bind(self, boxes: Mapping[str, SharedBox], box_key: str, command: str) -> None:
        """Say which command of which box this backend runs."""
        self._boxes = boxes
        self._box_key = box_key
        self._command = command

    def source(self, name: str) -> str:
        """Return the location of the command."""
        return (
            f"sharedbox://{_attached_name(self._boxes, self._box_key)}/{self._command}"
        )

    async def connect(self, timeout: float) -> None:
        """Do nothing: the box is attached with the device."""

    async def execute(self) -> None:
        """Run the command and wait until the service has finished it.

        Raises
        ------
        BoxPutError
            The command raised in the service.
        """
        async with self._lock:
            await _request(self._boxes[self._box_key], self._command, self._command)


def _command_backend(signature: inspect.Signature | None) -> BoxCommandBackend:
    """Return a command backend, refusing a command with arguments or a result."""
    if signature is not None:
        raise TypeError(
            "the sharedbox transport carries only commands without arguments "
            f"or a result; got {signature}"
        )
    return BoxCommandBackend()


class BoxDeviceConnector(DeviceConnector):
    """Connect a device to the boxes of a service.

    The top device attaches the index and the boxes of the service and fills
    itself and its children from what the index describes. A child gets its
    part of the description from its parent.

    Parameters
    ----------
    declared_only
        Fill only the signals, commands and children the device declares,
        and skip the rest of what the service serves. Declared children
        follow the same rule, and a declared `DeviceVector` takes every
        entry the service serves.
    """

    mock_device_vector_children: ClassVar[list[int]] = [1, 2]

    def __init__(self, prefix: str = "", *, declared_only: bool = False) -> None:
        self._prefix = prefix
        self._declared_only = declared_only
        self._description: ControllerDescription | None = None
        self._boxes: dict[str, SharedBox] = {}
        self._is_child = False
        self._is_filled = False

    def create_children_from_annotations(self, device: Device) -> None:
        """Create the signals, commands and children the device declares."""
        if hasattr(self, "_filler"):
            return
        self._filler: DeviceFiller[
            BoxSignalBackend[SignalDatatype], BoxDeviceConnector, BoxCommandBackend
        ] = DeviceFiller(
            device=device,
            signal_backend_factory=BoxSignalBackend,
            device_connector_factory=BoxDeviceConnector,
            command_backend_factory=_command_backend,
        )
        for create in (
            self._filler.create_signals_from_annotations,
            self._filler.create_commands_from_annotations,
            self._filler.create_devices_from_annotations,
        ):
            list(create(filled=False))
        self._filler.check_created()

    async def connect_mock(self, device: Device, mock: DeviceMock[Device]) -> None:
        """Connect with mock backends, needing no service."""
        if isinstance(device, DeviceVector):
            self._filler.create_device_dict_entries_to_mock(
                self.mock_device_vector_children
            )
        device.set_name(device.name)
        await super().connect_mock(device, mock)

    async def connect_real(
        self, device: Device, timeout: float, force_reconnect: bool
    ) -> None:
        """Attach the boxes of the service, fill the device from them and connect it."""
        if not self._is_child and (self._description is None or force_reconnect):
            await self._attach(timeout)
        description = self._description
        assert description is not None
        if not self._is_filled:
            self._fill(device, description)
            self._is_filled = True
        where = description["box"] or controller_label(description)
        names = sorted(
            [
                *description["attributes"],
                *description["commands"],
                *description["children"],
            ]
        )
        self._filler.check_filled(f"{where}: {names}")
        device.set_name(device.name)
        await super().connect_real(device, timeout, force_reconnect)

    async def _attach(self, timeout: float) -> None:
        """Attach the index, retrying until `timeout`, then every box it names."""
        description = await self._read_index(timeout)
        if (
            self._is_filled
            and self._description is not None
            and (difference := _first_difference(self._description, description))
        ):
            raise RuntimeError(
                f"{difference} differs from what the device was filled from; "
                f"the device must be built again"
            )
        self._swap_boxes(self._attach_boxes(description))
        self._description = description

    async def _read_index(self, timeout: float) -> ControllerDescription:
        """Return the description the index box holds, retrying until `timeout`.

        Raises
        ------
        TimeoutError
            If no service publishes the index within `timeout`.
        """
        name = index_name(self._prefix)
        try:
            async with asyncio.timeout(timeout):
                while True:
                    try:
                        index = ServiceIndex.attach(name)
                        break
                    except SegmentNotFoundError:
                        await asyncio.sleep(_ATTACH_RETRY)
        except TimeoutError:
            raise TimeoutError(f"no sharedbox service publishes {name!r}") from None
        try:
            description: ControllerDescription = json.loads(index.description)
        finally:
            index.close()
        return description

    def _attach_boxes(self, description: ControllerDescription) -> dict[str, SharedBox]:
        """Attach the box of every controller in `description`, by key.

        The boxes attached so far are closed if one cannot be.
        """
        attached: dict[str, SharedBox] = {}
        try:
            for node in walk(description):
                if node["box"] is not None:
                    attached[_box_key(node)] = box_class(node).attach(node["box"])
        except BaseException:
            for box in attached.values():
                box.close()
            raise
        return attached

    def _swap_boxes(self, attached: Mapping[str, SharedBox]) -> None:
        """Put `attached` in place of the boxes held, closing those."""
        old = list(self._boxes.values())
        self._boxes.clear()
        self._boxes.update(attached)
        for box in old:
            box.close()

    def _fill(self, device: Device, description: ControllerDescription) -> None:
        """Create the signals, commands and children `description` names."""
        box = description["box"]
        declared = (
            {name for name, _ in device.children()}
            if self._declared_only and not isinstance(device, DeviceVector)
            else None
        )

        def wanted(name: str) -> bool:
            return declared is None or name in declared

        for name, attribute in description["attributes"].items():
            if wanted(name):
                assert box is not None
                backend = self._filler.fill_child_signal(
                    name, _SIGNALS[attribute["access"]]
                )
                backend._bind(self._boxes, _box_key(description), name, attribute)
        for name in description["commands"]:
            if wanted(name):
                assert box is not None
                self._filler.fill_child_command(name, TriggerableCommand)._bind(
                    self._boxes, _box_key(description), name
                )
        for key, child in description["children"].items():
            if wanted(key):
                self._fill_child(device, key, child)

    def _fill_child(
        self, device: Device, key: str, child: ControllerDescription
    ) -> None:
        """Create the child device `key` of `device`, filled from `child` on connect."""
        if isinstance(device, DeviceVector):
            connector = self._filler.fill_child_device(
                device.name, Device, map_key=int(key)
            )
        else:
            vector = bool(child["children"]) and all(
                part.isdigit() for part in child["children"]
            )
            connector = self._filler.fill_child_device(
                key, DeviceVector if vector else Device
            )
        connector._description = child
        connector._boxes = self._boxes
        connector._is_child = True
        connector._declared_only = self._declared_only
