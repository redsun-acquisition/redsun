"""Signal and slot wiring primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
    overload,
)

from psygnal import Signal, SignalGroup

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence
    from threading import Thread
    from typing import TypeAlias

    from ophyd_async.core import SignalR
    from psygnal import SignalInstance

__all__ = [
    "SLOT_ATTR",
    "SLOT_THREAD_ATTR",
    "ComponentNotBuilt",
    "Connection",
    "Link",
    "Ports",
    "Slot",
    "SlotThread",
    "Unconnected",
    "WiringError",
    "links_between",
    "marker_of",
    "owner_of",
    "port_name",
    "ports",
    "slot",
]

F = TypeVar("F", bound="Callable[..., Any]")

SLOT_ATTR = "__redsun_slot__"
SLOT_THREAD_ATTR = "__redsun_slot_thread__"

SlotThread: TypeAlias = "Literal['main', 'current'] | Thread | None"
"""Thread a slot is delivered on, as accepted by `psygnal`."""

SlotCallable: TypeAlias = "Callable[..., None] | Callable[..., Awaitable[None]]"
"""What a signal calls: a function returning nothing, or a coroutine function."""

Link: TypeAlias = "tuple[SignalInstance | SignalR[Any], SlotCallable]"
"""A signal and the slot it reaches, as a session's `wire` yields it."""


class WiringError(RuntimeError):
    """Raised when a connection between two components cannot be made."""


class ComponentNotBuilt(WiringError):
    """Raised when a port path names a component that is not there.

    `component` is the name the path used, so a caller that knows which
    components failed to build can tell one of those from a name that was
    never declared.
    """

    def __init__(self, component: str, message: str) -> None:
        super().__init__(message)
        self.component = component


@dataclass(frozen=True, slots=True)
class Slot:
    """What `slot` records on a method."""

    name: str | None
    """The port name, or `None` for the method's own name."""

    thread: SlotThread
    """The thread the slot is delivered on, or `None` for the component's default."""

    signals: tuple[str, ...]
    """Names of the other component's signals that reach this slot in a pairing."""


@overload
def slot(fn: F, /) -> F: ...
@overload
def slot(
    *,
    name: str | None = ...,
    thread: SlotThread = ...,
    signal: str | Sequence[str] = ...,
) -> Callable[[F], F]: ...
def slot(
    fn: F | None = None,
    /,
    *,
    name: str | None = None,
    thread: SlotThread = None,
    signal: str | Sequence[str] = (),
) -> F | Callable[[F], F]:
    """Mark a method as connectable to a signal.

    A marked method is public API: its name and signature are what other
    components are connected against, and an unmarked method cannot be
    connected at all. `async def` methods may be marked too.

    Parameters
    ----------
    fn
        The method, when the decorator is written bare. `None` when it is
        written with arguments, which returns the decorator itself.
    name
        Port name a configuration file addresses the method by. Defaults to
        the method name without leading underscores.
    thread
        Delivery thread, overriding the affinity the class declares.
    signal
        The signal, or the signals, that reach this slot when a session
        pairs its component with another: each is the attribute name of a
        signal of the other component. Without it, only the links a session
        lists reach the slot.
    """
    signals = (signal,) if isinstance(signal, str) else tuple(signal)

    def deco(target: F) -> F:
        setattr(target, SLOT_ATTR, Slot(name, thread, signals))
        return target

    return deco if fn is None else deco(fn)


def marker_of(method: object) -> Slot | None:
    """Return what `slot` recorded on *method*, `None` for one it did not mark."""
    marker = getattr(method, SLOT_ATTR, None)
    return marker if isinstance(marker, Slot) else None


def port_name(bound_slot: Callable[..., Any]) -> str:
    """Return the port name of a method marked with `slot`."""
    declaration = marker_of(bound_slot)
    if declaration is not None and declaration.name is not None:
        return declaration.name
    return getattr(bound_slot, "__name__", "<anonymous>").lstrip("_")


@dataclass(frozen=True, slots=True)
class Ports:
    """The connectable surface of a component."""

    signals: dict[str, SignalInstance] = field(default_factory=dict)
    """Signals, by port name."""

    slots: dict[str, Callable[..., Any]] = field(default_factory=dict)
    """Slots, by port name."""


def ports(component: object) -> Ports:
    """Return the signals and slots *component* exposes, by port name.

    A signal is a public [`Signal`][psygnal.Signal] attribute, or a member of a
    [`SignalGroup`][psygnal.SignalGroup] the component holds, in which case the
    member name is the port name. A slot is a method marked with `slot`.

    Parameters
    ----------
    component
        The built component to inspect.

    Raises
    ------
    WiringError
        If two signals claim the same port name, which would leave the
        component unaddressable.
    """
    cls = type(component)
    signals: dict[str, SignalInstance] = {}
    slots: dict[str, Callable[..., Any]] = {}

    for attr in dir(cls):
        declared = getattr(cls, attr, None)
        if isinstance(declared, Signal) and not attr.startswith("_"):
            signals[attr] = getattr(component, attr)
        elif marker_of(declared) is not None:
            method = getattr(component, attr)
            slots[port_name(method)] = method

    for group_name, value in getattr(component, "__dict__", {}).items():
        if isinstance(value, SignalGroup):
            for member in value:
                if member in signals:
                    raise WiringError(
                        f"{cls.__name__} exposes two signals named {member!r}: "
                        f"the member of group {group_name!r} and an attribute of "
                        "the same name"
                    )
                signals[member] = value[member]

    return Ports(signals=signals, slots=slots)


def links_between(a: object, b: object) -> list[Link]:
    """Return the links pairing two built components makes, both ways.

    Each signal of *a* reaches each slot of *b* naming it in its `signal`, then
    each signal of *b* reaches each slot of *a* naming it, in the order
    [`ports`][redsun.ports.ports] lists them. Only those signals are matched,
    so a device signal never is. An empty list means nothing matched.

    ```python
    def wire(self) -> Iterator[Link]:
        yield from links_between(self.motor_widget, self.motor_ctrl)
    ```

    Raises
    ------
    ValueError
        If *a* and *b* are one object.
    WiringError
        If either exposes two signals under one port name.
    """
    if a is b:
        raise ValueError(f"cannot pair {a!r} with itself")
    return [*one_way(a, b), *one_way(b, a)]


def one_way(sender: object, receiver: object) -> list[Link]:
    """Return the links from the signals of *sender* to the slots of *receiver* naming them."""
    slots = [
        (marker.signals, method)
        for method in ports(receiver).slots.values()
        if (marker := marker_of(method)) is not None
    ]
    return [
        (signal, method)
        for name, signal in ports(sender).signals.items()
        for names, method in slots
        if name in names
    ]


@dataclass(frozen=True, kw_only=True, slots=True)
class Connection:
    """A recorded link between a signal and a slot.

    The signal is a `psygnal` signal of a component, or a signal of a
    device, whose publisher is the device and whose port is the signal's name
    within it.
    """

    publisher: str
    """Name of the component or device that sends."""

    publisher_port: str
    """Name of the signal within the publisher."""

    consumer: str
    """Name of the component that receives."""

    consumer_port: str
    """Port name of the slot within the consumer."""

    thread: SlotThread = None
    """Thread the slot runs on. `None` is the thread that emits."""

    def __str__(self) -> str:
        thread = f"  [thread={self.thread}]" if self.thread else ""
        return (
            f"{self.publisher}.{self.publisher_port} -> "
            f"{self.consumer}.{self.consumer_port}{thread}"
        )


@dataclass(frozen=True, kw_only=True, slots=True)
class Unconnected:
    """Ports of the built components that no connection reaches.

    Each entry is a `component.port` path. A signal listed here emits into
    nothing; a slot listed here is never called.
    """

    signals: list[str] = field(default_factory=list)
    """Paths of the signals nothing listens to."""

    slots: list[str] = field(default_factory=list)
    """Paths of the slots nothing reaches."""

    def __bool__(self) -> bool:
        return bool(self.signals or self.slots)

    def __str__(self) -> str:
        if not self:
            return "every port is connected"
        lines = [f"{path} -> nothing" for path in self.signals]
        lines += [f"nothing -> {path}" for path in self.slots]
        return "\n".join(lines)


def owner_of(signal: SignalInstance) -> object | None:
    """Return the component a signal belongs to.

    A signal declared inside a `SignalGroup` reports the group as its
    instance, so the owning component is one level further out.
    """
    instance: object | None = signal.instance
    if isinstance(instance, SignalGroup):
        return cast("object | None", instance.instance)
    return instance
