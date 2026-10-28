from __future__ import annotations

import asyncio
import enum
import json
import time
from typing import TYPE_CHECKING, Any, ClassVar, get_origin

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

from redsun.log import logger
from redsun.services._layout import (
    AttributeDescription,
    ControllerDescription,
    ServiceIndex,
    box_class,
    index_name,
    stream_name,
)

if TYPE_CHECKING:
    import inspect
    from collections.abc import Mapping

__all__ = [
    "BoxCommandBackend",
    "BoxDeviceConnector",
    "BoxPutError",
    "BoxSignalBackend",
    "stream_name",
]

ATTACH_RETRY = 0.1
"""Seconds between attempts to attach a service's index."""

DATATYPES: dict[str, type] = {
    "int": int,
    "uint": int,
    "float": float,
    "bool": bool,
    "str": str,
    "waveform": np.ndarray,
}
"""Python type of each datatype kind a description names, enums apart."""

SIGNALS = {"r": SignalR, "w": SignalW, "rw": SignalRW}


class BoxPutError(Exception):
    """A service refused a write or a command, or it raised while running it."""

    def __init__(self, attribute: str, message: str) -> None:
        super().__init__(f"{attribute}: {message}")
        self.attribute = attribute


def box_key(description: ControllerDescription) -> str:
    """Return the key of the box of `description`, the same across runs of a service."""
    return ":".join(description["path"])


async def request(box: Any, stem: str, name: str, **values: Any) -> None:
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
        self._boxes: Mapping[str, Any] = {}
        self._box_key = ""
        self._attribute = ""
        self._description: AttributeDescription
        self._names: list[str] = []
        self._readback = ""
        self._lock = asyncio.Lock()
        self._callback: Any = None
        self._follower: asyncio.Task[None] | None = None

    def _bind(
        self,
        boxes: Mapping[str, Any],
        box_key: str,
        attribute: str,
        description: AttributeDescription,
    ) -> None:
        """Say which attribute of which box this backend reads and writes."""
        self._boxes = boxes
        self._box_key = box_key
        self._attribute = attribute
        self._description = description
        self._names = description["datatype"].get("names", [])
        field = "value" if "r" in description["access"] else "setpoint"
        self._readback = f"{attribute}__{field}"

    def _box_name(self) -> str:
        """Return the name of the attached box, the key before it is attached."""
        box = self._boxes.get(self._box_key)
        return self._box_key if box is None else str(box.name)

    def _box(self) -> Any:
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
        kind = self._description["datatype"]["kind"]
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
            if self._callback:
                self._follow_readback()
            return
        expected = DATATYPES[kind]
        if self.datatype is None:
            self.datatype = expected
        elif (get_origin(self.datatype) or self.datatype) is not expected:
            self._mismatch(expected.__name__)
        if self._callback:
            self._follow_readback()

    def _mismatch(self, served: str) -> None:
        """Raise the error of a declared datatype the service does not serve."""
        raise TypeError(
            f"{self._box_name()}: {self._attribute} is declared as {self.datatype} "
            f"but the service serves {served}"
        )

    def _from_box(self, raw: Any) -> Any:
        """Return the value a box field holds, as the signal's datatype."""
        match self._description["datatype"]["kind"]:
            case "uint":
                return int(raw[0])
            case "enum":
                choices: Any = self.datatype
                return choices(self._names[raw])
            case "waveform":
                return np.array(raw)
        return raw

    def _to_box(self, value: Any) -> Any:
        """Return the box field content holding `value`."""
        datatype = self._description["datatype"]
        match datatype["kind"]:
            case "uint":
                return np.array([value], dtype="uint64")
            case "enum":
                return self._names.index(
                    value.value if isinstance(value, enum.Enum) else value
                )
            case "waveform":
                padded = np.zeros(datatype["shape"], dtype=datatype["dtype"])
                padded[tuple(slice(0, size) for size in np.shape(value))] = value
                return padded
        return value

    def _current(self) -> Reading[Any]:
        """Return the current value as a reading."""
        raw = getattr(self._box(), self._readback)
        if self._description["datatype"]["kind"] == "waveform":
            shape = getattr(self._box(), f"{self._attribute}__shape")
            raw = raw[tuple(slice(0, size) for size in shape)]
        return Reading(
            value=self._from_box(raw), timestamp=time.time(), alarm_severity=0
        )

    async def put(self, value: SignalDatatypeT | None) -> None:
        """Write `value` and wait until the service has put it.

        Raises
        ------
        BoxPutError
            The service refused the value or its put raised.
        """
        async with self._lock:
            await request(
                self._box(),
                self._attribute,
                self._attribute,
                **{f"{self._attribute}__setpoint": self._to_box(value)},
            )

    async def get_datakey(self, source: str) -> Any:
        """Return the data key, with the units, precision, limits and choices served."""
        datatype: Mapping[str, Any] = self._description["datatype"]
        metadata = SignalMetadata()
        if "units" in datatype:
            metadata["units"] = datatype["units"]
        if "precision" in datatype:
            metadata["precision"] = datatype["precision"]
        if datatype["kind"] == "enum":
            metadata["choices"] = self._names
        limits = Limits()
        for key, low, high in (
            ("control", "min", "max"),
            ("alarm", "min_alarm", "max_alarm"),
        ):
            if low in datatype or high in datatype:
                limits[key] = LimitsRange(  # type: ignore[literal-required]
                    low=datatype.get(low), high=datatype.get(high)
                )
        if limits:
            metadata["limits"] = limits
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
        return self._current()["value"]  # type: ignore[no-any-return]

    async def get_setpoint(self) -> SignalDatatypeT:
        """Return the last value written."""
        if "w" not in self._description["access"]:
            return await self.get_value()
        return self._from_box(getattr(self._box(), f"{self._attribute}__setpoint"))  # type: ignore[no-any-return]

    def set_callback(self, callback: Any) -> None:
        """Call `callback` with the current reading, then with each new one."""
        if callback and self._callback:
            raise RuntimeError("Cannot set a callback when one is already set")
        self._callback = callback
        if callback:
            self._follow_readback()
        elif self._follower is not None:
            self._follower.cancel()
            self._follower = None

    def _follow_readback(self) -> None:
        """Call the callback with the current reading, then follow the box's value."""
        if self._follower is not None:
            self._follower.cancel()
        watch = self._box().watch(self._readback)
        self._callback(self._current())
        self._follower = asyncio.create_task(self._follow(watch))

    async def _follow(self, watch: Any) -> None:
        """Call the callback with the reading after each write to the value."""
        try:
            async for _ in watch:
                try:
                    self._callback(self._current())
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
        self._boxes: Mapping[str, Any] = {}
        self._box_key = ""
        self._command = ""
        self._lock = asyncio.Lock()

    def _bind(self, boxes: Mapping[str, Any], box_key: str, command: str) -> None:
        """Say which command of which box this backend runs."""
        self._boxes = boxes
        self._box_key = box_key
        self._command = command

    def source(self, name: str) -> str:
        """Return the location of the command."""
        box = self._boxes.get(self._box_key)
        return (
            f"sharedbox://{self._box_key if box is None else box.name}/{self._command}"
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
            await request(self._boxes[self._box_key], self._command, self._command)


def command_backend(signature: inspect.Signature | None) -> BoxCommandBackend:
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
    """

    mock_device_vector_children: ClassVar[list[int]] = [1, 2]

    def __init__(self, prefix: str = "") -> None:
        self._prefix = prefix
        self._description: ControllerDescription | None = None
        self._boxes: dict[str, Any] = {}
        self._is_child = False
        self._is_filled = False

    def create_children_from_annotations(self, device: Device) -> None:
        """Create the signals, commands and children the device declares."""
        if hasattr(self, "filler"):
            return
        self._filler: DeviceFiller[Any, BoxDeviceConnector, BoxCommandBackend] = (
            DeviceFiller(
                device=device,
                signal_backend_factory=BoxSignalBackend,
                device_connector_factory=BoxDeviceConnector,
                command_backend_factory=command_backend,
            )
        )
        for create in (
            self._filler.create_signals_from_annotations,
            self._filler.create_commands_from_annotations,
            self._filler.create_devices_from_annotations,
        ):
            list(create(filled=False))
        self._filler.check_created()

    async def connect_mock(self, device: Device, mock: DeviceMock[Any]) -> None:
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
        where = description["box"] or ":".join(["root", *description["path"]])
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
        name = index_name(self._prefix)
        try:
            async with asyncio.timeout(timeout):
                while True:
                    try:
                        index = ServiceIndex.attach(name)
                        break
                    except SegmentNotFoundError:
                        await asyncio.sleep(ATTACH_RETRY)
        except TimeoutError:
            raise TimeoutError(f"no sharedbox service publishes {name!r}") from None
        try:
            description: ControllerDescription = json.loads(index.description)
        finally:
            index.close()
        attached: dict[str, Any] = {}
        try:
            self._attach_boxes(description, attached)
        except BaseException:
            for box in attached.values():
                box.close()
            raise
        old = list(self._boxes.values())
        self._boxes.clear()
        self._boxes.update(attached)
        for box in old:
            box.close()
        self._description = description

    def _attach_boxes(
        self, description: ControllerDescription, attached: dict[str, Any]
    ) -> None:
        """Attach the box of `description` and of every child below it."""
        if description["box"] is not None:
            attached[box_key(description)] = box_class(description).attach(
                description["box"]
            )
        for child in description["children"].values():
            self._attach_boxes(child, attached)

    def _fill(self, device: Device, description: ControllerDescription) -> None:
        """Create the signals, commands and children `description` names."""
        box = description["box"]
        for name, attribute in description["attributes"].items():
            assert box is not None
            backend = self._filler.fill_child_signal(name, SIGNALS[attribute["access"]])
            backend._bind(self._boxes, box_key(description), name, attribute)
        for name in description["commands"]:
            assert box is not None
            self._filler.fill_child_command(name, TriggerableCommand)._bind(
                self._boxes, box_key(description), name
            )
        for key, child in description["children"].items():
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
