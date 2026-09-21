from __future__ import annotations

import os
import socket
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

__all__ = [
    "CHANNEL_ACCESS",
    "PV_ACCESS",
    "TRANSPORTS",
    "TRANSPORT_KEY",
    "Transport",
    "checked_transport",
    "transport_of",
]

CHANNEL_ACCESS: Final = "channel-access"
"""The protocol a session's services speak unless it says otherwise."""

PV_ACCESS: Final = "pv-access"
"""The other protocol a session may name."""

TRANSPORT_KEY: Final = "transport"
"""The key of the ``services`` section naming what its services speak."""

LOOPBACK: Final = "127.0.0.1"
"""Where a launched service listens, and where this process looks for it."""


class Transport(Protocol):
    """What a control-system protocol needs of the process on each side.

    A session has one, which every service of it uses: the variables the
    protocols read are per process, so two of them in one session would leave
    each unable to say which service a variable is for.
    """

    name: str

    def reserve(self, service: str) -> Mapping[str, str]:
        """Return the environment the process of *service* is launched with."""
        ...

    def publish(self, service: str) -> None:
        """Tell this process where *service* answers.

        Called once per start. An implementation that has nothing to add for a
        service it already published does nothing.
        """
        ...

    async def release(self) -> None:
        """Drop what this process caches about services of this transport."""
        ...


class ChannelAccess:
    """Channel Access, each service answering on a port of its own.

    A client reads ``EPICS_CA_ADDR_LIST`` once, when it first uses Channel
    Access, so a service restarted by a rebuilt container keeps the port the
    list already holds.
    """

    name = CHANNEL_ACCESS

    def __init__(self) -> None:
        self._ports: dict[str, int] = {}
        self._published: set[str] = set()

    def reserve(self, service: str) -> Mapping[str, str]:
        """Return the service's own Channel Access server port."""
        return {"EPICS_CA_SERVER_PORT": str(self._port(service))}

    def publish(self, service: str) -> None:
        """Add the service's port to this process's address list, once.

        A restarted service keeps its port, so the list it is already in needs
        nothing added: a client read it when it first used Channel Access.
        """
        if service in self._published:
            return
        self._published.add(service)
        add_to_env("EPICS_CA_ADDR_LIST", f"127.0.0.1:{self._port(service)}")

    async def release(self) -> None:
        """Close every Channel Access channel this process holds, if it holds any.

        Otherwise a channel to a stopped service waits out libca's reconnect
        delay, about ten seconds, before a rebuilt device reaches the restarted
        service. Every channel in the process is closed, since libca offers
        nothing narrower.
        """
        try:
            from aioca import purge_channel_caches
        except ImportError:
            return
        purge_channel_caches()

    def _port(self, service: str) -> int:
        """Return the service's port, taking a free one the first time."""
        if service not in self._ports:
            # the system may hand out a port it already gave another service
            port = free_udp_port()
            while port in self._ports.values():
                port = free_udp_port()
            self._ports[service] = port
        return self._ports[service]


class PVAccess:
    """PVAccess, every service of the session on the loopback interface.

    A service picks its own ports: ``pvxs`` takes another TCP port when the
    default one is busy, and local servers share the search port, so several
    answer without the session assigning anything. What a client cannot do by
    itself is reach a service bound to the loopback, which its defaults never
    search, so this process is told that address.
    """

    name = PV_ACCESS

    def __init__(self) -> None:
        self._published = False

    def reserve(self, service: str) -> Mapping[str, str]:
        """Keep the service on the loopback, as a Channel Access one is."""
        return {"EPICS_PVAS_INTF_ADDR_LIST": LOOPBACK}

    def publish(self, service: str) -> None:
        """Add the loopback to this process's address list, once for them all.

        ``EPICS_PVA_AUTO_ADDR_LIST`` is left alone, so a session still reaches
        the servers of its site.
        """
        if self._published:
            return
        self._published = True
        add_to_env("EPICS_PVA_ADDR_LIST", LOOPBACK)

    async def release(self) -> None:
        """Nothing: a client reaches a restarted service without being told."""


TRANSPORTS: dict[str, Transport] = {
    CHANNEL_ACCESS: ChannelAccess(),
    PV_ACCESS: PVAccess(),
}
"""The transports a session may name, by the name a session file writes."""


def transport_of(config: Mapping[str, Any]) -> Any:
    """Return what a configuration names under ``services.transport``.

    ``None`` when it names nothing. Whatever it wrote otherwise, a string
    or not: the caller says what a mapping there means.
    """
    services = config.get("services") or {}
    return services.get(TRANSPORT_KEY) if isinstance(services, dict) else None


def checked_transport(name: str, where: str) -> str:
    """Return *name*, refusing a transport ``redsun`` does not have.

    Raises
    ------
    TypeError
        Naming what was read and the transports there are.
    """
    if name not in TRANSPORTS:
        known = ", ".join(repr(key) for key in sorted(TRANSPORTS))
        raise TypeError(f"{where} asks for transport {name!r}; redsun has {known}")
    return name


def add_to_env(name: str, value: str) -> None:
    """Append *value* to the environment variable *name*, space separated."""
    os.environ[name] = " ".join(filter(None, [os.environ.get(name), value]))


def free_udp_port() -> int:
    """Return a UDP port on the loopback interface that nothing is bound to.

    The port is free when read; nothing holds it for the caller, so another
    program can bind it first, and a later call may return it again.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port
