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
    "transport_of",
]

CHANNEL_ACCESS: Final = "channel-access"
"""The protocol a session's services speak unless it says otherwise."""

PV_ACCESS: Final = "pv-access"
"""The other protocol a session may name."""

TRANSPORT_KEY: Final = "transport"
"""The key of the `services` section naming what its services speak."""

LOOPBACK: Final = "127.0.0.1"
"""Where a launched service listens, and where this process looks for it."""


class Transport(Protocol):
    """What a control-system protocol needs of the process on each side.

    A session has one, which every service of it uses.
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

    def attach(self, address: str) -> None:
        """Tell this process to look for services at *address*, unless it already does."""
        ...

    async def release(self) -> None:
        """Drop what this process caches about services of this transport."""
        ...


class ChannelAccess:
    """Channel Access, each service answering on a port of its own.

    A client reads `EPICS_CA_ADDR_LIST` once, when it first uses Channel
    Access, so a service restarted by a rebuilt container keeps the port the
    list already holds.
    """

    name = CHANNEL_ACCESS

    def __init__(self) -> None:
        self._ports: dict[str, int] = {}

    def reserve(self, service: str) -> Mapping[str, str]:
        """Return the service's own Channel Access server port."""
        return {"EPICS_CA_SERVER_PORT": str(self._port(service))}

    def publish(self, service: str) -> None:
        """Add the service's port to this process's address list, unless listed.

        A restarted service keeps its port, so the list it is already in needs
        nothing added: a client read it when it first used Channel Access.
        """
        add_to_env("EPICS_CA_ADDR_LIST", f"{LOOPBACK}:{self._port(service)}")

    def attach(self, address: str) -> None:
        """Add *address* to this process's Channel Access address list."""
        add_to_env("EPICS_CA_ADDR_LIST", address)

    async def release(self) -> None:
        """Close every Channel Access channel this process holds, if it holds any."""
        try:
            from aioca import purge_channel_caches  # noqa: PLC0415
        except ImportError:
            return
        # a channel left to a stopped service waits out libca's reconnect
        # delay, about ten seconds, before a rebuilt device reaches the
        # restarted one; libca offers nothing narrower than every channel
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

    A service picks its own ports: `pvxs` takes another TCP port when the
    default one is busy, and local servers share the search port, so several
    answer without the session assigning anything. What a client cannot do by
    itself is reach a service bound to the loopback, which its defaults never
    search, so this process is told that address.
    """

    name = PV_ACCESS

    def reserve(self, service: str) -> Mapping[str, str]:
        """Keep the service on the loopback, on any free TCP port.

        Told no port, a server tries the default one first, which the second
        server of a session is refused and warns about before it falls back
        to a free one. Told port 0, it takes a free one at once.
        """
        return {"EPICS_PVAS_INTF_ADDR_LIST": LOOPBACK, "EPICS_PVAS_SERVER_PORT": "0"}

    def publish(self, service: str) -> None:
        """Add the loopback to this process's address list, unless listed.

        `EPICS_PVA_AUTO_ADDR_LIST` is left alone, so a session still reaches
        the servers of its site.
        """
        add_to_env("EPICS_PVA_ADDR_LIST", LOOPBACK)

    def attach(self, address: str) -> None:
        """Add *address* to this process's PVAccess address list."""
        add_to_env("EPICS_PVA_ADDR_LIST", address)

    async def release(self) -> None:
        """Nothing: a client reaches a restarted service without being told."""


TRANSPORTS: dict[str, Transport] = {
    CHANNEL_ACCESS: ChannelAccess(),
    PV_ACCESS: PVAccess(),
}
"""The transports a session may name, by the name a session file writes."""


def transport_of(config: Mapping[str, Any]) -> Any:
    """Return what a configuration names under `services.transport`.

    `None` when it names nothing. Whatever it wrote otherwise, a string
    or not: the caller says what a mapping there means.
    """
    services = config.get("services") or {}
    return services.get(TRANSPORT_KEY) if isinstance(services, dict) else None


def add_to_env(name: str, value: str) -> None:
    """Append *value* to the space-separated variable *name*, unless it is listed."""
    listed = os.environ.get(name, "").split()
    if value not in listed:
        os.environ[name] = " ".join([*listed, value])


def free_udp_port() -> int:
    """Return a UDP port on the loopback interface that nothing is bound to.

    The port is free when read; nothing holds it for the caller, so another
    program can bind it first, and a later call may return it again.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((LOOPBACK, 0))
        port: int = sock.getsockname()[1]
    return port
