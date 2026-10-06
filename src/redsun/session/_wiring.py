"""The links of a session: made, recorded and undone."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast, overload

from ophyd_async.core import SignalR
from psygnal import SignalInstance

from redsun.aio import run_coro
from redsun.path_provider import PATH_PROVIDER_PORT
from redsun.ports import (
    ComponentNotBuilt,
    Connection,
    Unconnected,
    WiringError,
    links_between,
    ports,
)

from ..ports._wiring import SLOT_THREAD_ATTR, marker_of, owner_of, port_name

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from redsun.path_provider import SessionPathProvider
    from redsun.ports import SlotThread

    from ..ports._wiring import SlotCallable
    from ._frontend import Frontend

__all__ = ["NotBuilt", "Wiring", "skipped"]

logger = logging.getLogger("redsun")


@dataclass(frozen=True)
class NotBuilt:
    """Stands in for a component that failed to build, while `Session.wire` runs.

    Any attribute read on it is another stand-in for the same component, so
    a link yielding `self.stage.readback` is recognised and skipped.
    """

    component: str
    """The component that failed to build."""

    port: str = ""
    """The attribute read on it, empty for the component itself."""

    def __getattr__(self, name: str) -> NotBuilt:
        if name.startswith("__"):
            raise AttributeError(name)
        return NotBuilt(self.component, name)

    def __str__(self) -> str:
        return f"{self.component}.{self.port}" if self.port else self.component


def skipped(*ends: object) -> bool:
    """Warn and return true when an end of a link stands in for a failed component."""
    failed = next((end for end in ends if isinstance(end, NotBuilt)), None)
    if failed is None:
        return False
    logger.warning(
        "Not connecting %s: component %r was not built", failed, failed.component
    )
    return True


class Wiring:
    """The links of a session: made, recorded and undone.

    The mappings of built components, of their names and of the components
    that failed are the session's own, filled in place, so each component is
    seen here as soon as it is built.
    """

    __slots__ = (
        "components",
        "connections",
        "failed",
        "frontend",
        "links",
        "names",
        "path_provider",
        "subscriptions",
    )

    def __init__(
        self,
        components: Mapping[str, object],
        names: Mapping[int, str],
        failed: Mapping[str, BaseException],
        frontend: type[Frontend],
    ) -> None:
        self.components = components
        self.names = names
        self.failed = failed
        self.frontend = frontend
        # made by the session while it reads its configuration, after this
        self.path_provider: SessionPathProvider | None = None
        self.links: list[tuple[SignalInstance, SlotCallable]] = []
        self.connections: list[Connection] = []
        # the forwarding function is held because ophyd-async releases a
        # subscription by identity: clear_sub needs the object back
        self.subscriptions: list[
            tuple[SignalR[Any], SlotCallable, Callable[[Any], None], SignalInstance]
        ] = []

    def label(self, owner: object | None) -> str:
        """Return the name of the component *owner* is, or is held by.

        An object a component keeps as an attribute, with ports of its own,
        is named after that component.
        """
        if owner is None:
            return "<unknown>"
        if id(owner) in self.names:
            return self.names[id(owner)]
        for name, component in self.components.items():
            held = getattr(component, "__dict__", {}).values()
            if any(value is owner for value in held):
                return name
        return type(owner).__name__

    def affinity(self, slot: Callable[..., Any]) -> SlotThread:
        """Return the thread *slot* is delivered on.

        Raises
        ------
        WiringError
            If *slot* is not marked as connectable.
        """
        declaration = marker_of(slot)
        if declaration is None:
            name = getattr(slot, "__qualname__", repr(slot))
            raise WiringError(
                f"{name} is not connectable; mark it with the 'slot' decorator"
            )
        consumer = getattr(slot, "__self__", None)
        return (
            declaration.thread
            or cast("SlotThread", getattr(type(consumer), SLOT_THREAD_ATTR, None))
            or self.frontend.thread_of(consumer)
        )

    def link(self, signal: object, slot: SlotCallable) -> None:
        """Make one link, unless it is made already or an end of it failed to build.

        Raises
        ------
        WiringError
            If *signal* is not a signal, if *slot* is not marked as
            connectable, or if psygnal rejects the two signatures.
        """
        if skipped(signal, slot):
            return
        made = [
            *self.links,
            *((sent, reached) for sent, reached, _, _ in self.subscriptions),
        ]
        if any(sent is signal and reached == slot for sent, reached in made):
            logger.debug(
                "Not connecting %s to %s.%s again",
                getattr(signal, "name", signal),
                self.label(getattr(slot, "__self__", None)),
                port_name(slot),
            )
            return
        if isinstance(signal, SignalInstance):
            self.connect(signal, slot)
        elif isinstance(signal, SignalR):
            self.subscribe(signal, slot)
        else:
            raise WiringError(
                f"{signal!r} is not a signal; a link is a psygnal signal or a "
                "device signal, then the slot it reaches"
            )

    def connect(self, signal: SignalInstance, slot: SlotCallable) -> None:
        """Connect a `psygnal` signal to *slot* and record the connection."""
        thread = self.affinity(slot)
        link = Connection(
            publisher=self.label(owner_of(signal)),
            publisher_port=signal.name or "<anonymous>",
            consumer=self.label(getattr(slot, "__self__", None)),
            consumer_port=port_name(slot),
            thread=thread,
        )
        try:
            signal.connect(slot, thread=thread)
        except (TypeError, ValueError) as e:
            raise WiringError(f"cannot connect {link}: {e}") from e

        self.links.append((signal, slot))
        self.connections.append(link)
        logger.debug(f"Connected {link}")

    def subscribe(self, signal: SignalR[Any], slot: SlotCallable) -> None:
        """Deliver every reading of a device signal to *slot*, and record it."""
        # ophyd-async calls a subscriber on whatever thread produced the
        # reading, so the reading goes through a psygnal signal to reach the
        # thread the slot asks for
        thread = self.affinity(slot)
        relay = SignalInstance((object,), name=signal.name)
        relay.connect(slot, thread=thread)

        # kept as one object: unsubscribing goes by identity
        forward = relay.emit

        # a device names its signals after itself, as device-signal
        device, _, port = signal.name.partition("-")
        link = Connection(
            publisher=device if port else self.label(None),
            publisher_port=port or signal.name,
            consumer=self.label(getattr(slot, "__self__", None)),
            consumer_port=port_name(slot),
            thread=thread,
        )

        async def attach() -> None:
            signal.subscribe_reading(forward)

        # ophyd-async requires a running loop to subscribe, and callers run on
        # the main thread during the build
        run_coro(attach())
        self.subscriptions.append((signal, slot, forward, relay))
        self.connections.append(link)
        logger.debug(f"Connected {link}")

    def link_paths(self, source: str, target: str) -> None:
        """Connect two ports addressed as `component.port`.

        A path naming a component that failed to build is logged and skipped,
        so one component that could not be made does not keep the session from
        coming up. Every other way of getting a path wrong stays fatal.

        Raises
        ------
        WiringError
            If either path is malformed, names a component that was never
            declared, or names a port that component does not expose.
        """
        try:
            signal = self.resolve(source, "signal")
            slot = self.resolve(target, "slot")
        except ComponentNotBuilt as e:
            if e.component not in self.failed:
                raise
            logger.warning(
                "Not connecting %s -> %s: component %r was not built",
                source,
                target,
                e.component,
            )
            return
        self.link(signal, slot)

    def link_pair(self, first: str, second: str) -> None:
        """Make every link [`links_between`][redsun.links_between] finds for two.

        A pairing naming a component that failed to build is warned about and
        skipped.

        Raises
        ------
        WiringError
            If a name is neither a built component nor one that failed, or if
            both built and no signal of either reaches a slot of the other.
        """
        names = (first, second)
        unknown = [
            name
            for name in names
            if name not in self.components and name not in self.failed
        ]
        if unknown:
            known = ", ".join(sorted(self.components)) or "none"
            raise WiringError(
                f"pairs names {unknown[0]!r}, which is not a built presenter or "
                f"view. Built: {known}"
            )
        failed = [name for name in names if name in self.failed]
        if failed:
            logger.warning(
                "Not pairing %s with %s: component %r was not built",
                first,
                second,
                failed[0],
            )
            return
        links = links_between(self.components[first], self.components[second])
        if not links:
            raise WiringError(
                f"pairing {first!r} with {second!r} connects nothing: no slot of "
                "either names a signal of the other"
            )
        for signal, slot in links:
            self.link(signal, slot)

    @overload
    def resolve(self, path: str, kind: Literal["signal"]) -> SignalInstance: ...
    @overload
    def resolve(self, path: str, kind: Literal["slot"]) -> SlotCallable: ...
    def resolve(
        self, path: str, kind: Literal["signal", "slot"]
    ) -> SignalInstance | SlotCallable:
        """Look up the signal or slot a `component.port` path names."""
        component_name, _, port = path.partition(".")
        if not component_name or not port or "." in port:
            raise WiringError(f"{path!r} is not a port path; expected 'component.port'")
        component = (
            self.path_provider
            if component_name == PATH_PROVIDER_PORT
            else self.components.get(component_name)
        )
        if component is None:
            known = ", ".join(sorted(self.components)) or "none"
            raise ComponentNotBuilt(
                component_name,
                f"{path!r} names component {component_name!r}, which was not "
                f"built. Built: {known}",
            )
        surface = ports(component)
        available = surface.signals if kind == "signal" else surface.slots
        if port not in available:
            known = ", ".join(sorted(available)) or "none"
            raise WiringError(
                f"{component_name!r} exposes no {kind} named {port!r}. "
                f"Its {kind} ports: {known}"
            )
        return available[port]

    def unconnected(self) -> Unconnected:
        """Return the ports of the built components that no connection reaches.

        Raises
        ------
        WiringError
            If a component exposes two signals under one port name.
        """
        used_signals = {(c.publisher, c.publisher_port) for c in self.connections}
        used_slots = {(c.consumer, c.consumer_port) for c in self.connections}

        signals: list[str] = []
        slots: list[str] = []
        for name, component in self.components.items():
            surface = ports(component)
            signals += [
                f"{name}.{port}"
                for port in surface.signals
                if (name, port) not in used_signals
            ]
            slots += [
                f"{name}.{port}"
                for port in surface.slots
                if (name, port) not in used_slots
            ]
        return Unconnected(signals=signals, slots=slots)

    def undo(self) -> None:
        """Undo every connection and subscription made, and forget them."""
        for signal, slot in self.links:
            signal.disconnect(slot, missing_ok=True)
        self.links.clear()
        self.connections.clear()

        async def release(signal: SignalR[Any], forward: Callable[[Any], None]) -> None:
            signal.clear_sub(forward)

        for device_signal, _, forward, relay in self.subscriptions:
            run_coro(release(device_signal, forward))
            relay.disconnect()
        self.subscriptions.clear()
