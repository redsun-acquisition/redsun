from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    overload,
)

from psygnal import Signal, SignalGroup

if TYPE_CHECKING:
    from collections.abc import Callable
    from threading import Thread
    from typing import TypeAlias

    from psygnal import SignalInstance

__all__ = [
    "ComponentNotBuilt",
    "Connection",
    "Ports",
    "SlotThread",
    "Subscription",
    "Unconnected",
    "WiringError",
    "ports",
    "slot",
]

F = TypeVar("F", bound="Callable[..., Any]")

SLOT_ATTR = "__redsun_slot__"
SLOT_THREAD_ATTR = "__redsun_slot_thread__"

SlotThread: TypeAlias = "Literal['main', 'current'] | Thread | None"
"""Thread a slot is delivered on, as accepted by `psygnal`."""


class WiringError(RuntimeError):
    """Raised when a connection between two components cannot be made."""


class ComponentNotBuilt(WiringError):
    """Raised when a port path names a component that is not there.

    ``component`` is the name the path used, so a caller that knows which
    components failed to build can tell one of those from a name that was
    never declared.
    """

    def __init__(self, component: str, message: str) -> None:
        super().__init__(message)
        self.component = component


class Slot:
    """What [`slot`][redsun.virtual.slot] records on a method."""

    __slots__ = ("name", "thread")

    def __init__(self, name: str | None, thread: SlotThread) -> None:
        self.name = name
        self.thread = thread


@overload
def slot(fn: F, /) -> F: ...
@overload
def slot(*, name: str | None = ..., thread: SlotThread = ...) -> Callable[[F], F]: ...
def slot(
    fn: F | None = None,
    /,
    *,
    name: str | None = None,
    thread: SlotThread = None,
) -> F | Callable[[F], F]:
    """Mark a method as connectable to a signal.

    A marked method is public API: its name and signature are what other
    components are connected against, and an unmarked method cannot be
    connected at all. `async def` methods may be marked too.

    Parameters
    ----------
    name : str | None
        Port name a configuration file addresses the method by. Defaults to
        the method name without leading underscores.
    thread : SlotThread
        Delivery thread, overriding the affinity the class declares.
    """

    def deco(target: F) -> F:
        setattr(target, SLOT_ATTR, Slot(name, thread))
        return target

    return deco if fn is None else deco(fn)


def port_name(bound_slot: Callable[..., Any]) -> str:
    """Return the port name of a method marked with [`slot`][redsun.virtual.slot]."""
    declaration: Slot | None = getattr(bound_slot, SLOT_ATTR, None)
    if declaration is not None and declaration.name is not None:
        return declaration.name
    return getattr(bound_slot, "__name__", "<anonymous>").lstrip("_")


@dataclass(frozen=True, slots=True)
class Ports:
    """The connectable surface of a component."""

    signals: dict[str, SignalInstance] = field(default_factory=dict)
    slots: dict[str, Callable[..., Any]] = field(default_factory=dict)


def ports(component: object) -> Ports:
    """Return the signals and slots *component* exposes, by port name.

    A signal is a public [`Signal`][psygnal.Signal] attribute, or a member of a
    [`SignalGroup`][psygnal.SignalGroup] the component holds, in which case the
    member name is the port name. A slot is a method marked with `slot`.

    Parameters
    ----------
    component : object
        The built component to inspect.

    Returns
    -------
    Ports
        Its signals and slots, keyed by port name.

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
        elif isinstance(getattr(declared, SLOT_ATTR, None), Slot):
            slots[port_name(getattr(component, attr))] = getattr(component, attr)

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


@dataclass(frozen=True, kw_only=True, slots=True)
class Connection:
    """A recorded link between a signal and a slot."""

    publisher: str
    publisher_port: str
    consumer: str
    consumer_port: str
    thread: SlotThread = None

    def __str__(self) -> str:
        thread = f"  [thread={self.thread}]" if self.thread else ""
        return (
            f"{self.publisher}.{self.publisher_port} -> "
            f"{self.consumer}.{self.consumer_port}{thread}"
        )


@dataclass(frozen=True, kw_only=True, slots=True)
class Unconnected:
    """Ports of the built components that no connection reaches.

    Each entry is a ``component.port`` path. A signal listed here emits into
    nothing; a slot listed here is never called.
    """

    signals: list[str] = field(default_factory=list)
    slots: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.signals or self.slots)

    def __str__(self) -> str:
        if not self:
            return "every port is connected"
        lines = [f"{path} -> nothing" for path in self.signals]
        lines += [f"nothing -> {path}" for path in self.slots]
        return "\n".join(lines)


@dataclass(frozen=True, kw_only=True, slots=True)
class Subscription:
    """A recorded subscription to a device signal."""

    source: str
    consumer: str
    consumer_port: str
    thread: SlotThread = None

    def __str__(self) -> str:
        thread = f"  [thread={self.thread}]" if self.thread else ""
        return f"{self.source} ~> {self.consumer}.{self.consumer_port}{thread}"
