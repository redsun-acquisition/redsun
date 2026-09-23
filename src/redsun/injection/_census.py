from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    TypeAlias,
    TypeVar,
    get_args,
    get_origin,
)

from .._structural import members, problems, protocol_of, satisfies

if TYPE_CHECKING:
    from typing_extensions import TypeForm

__all__ = ["Devices", "DevicesOf", "devices_protocol", "rejected", "satisfying"]


@dataclass(frozen=True)
class Devices:
    """Marks a constructor parameter the session fills with devices."""


P = TypeVar("P")

DevicesOf: TypeAlias = Annotated[Mapping[str, P], Devices()]
"""Every device of the session that satisfies *P*, by name.

```python
class MotorProtocol(Protocol):
    async def set(self, value: float) -> None: ...


class MotorPresenter:
    def __init__(self, name: str, *, motors: DevicesOf[MotorProtocol]) -> None:
        self._motors = motors
```

Devices are built before any presenter or view, so the mapping arrives
complete and may be read while the component is built. Ask for
`redsun.DeviceMapping` instead to receive every device,
unfiltered.
"""


def devices_protocol(hint: object) -> type | None:
    """Return the protocol a ``DevicesOf`` annotation names, or ``None`` for another hint.

    Raises
    ------
    TypeError
        If *hint* carries the `Devices` marker on anything but
        ``Mapping[str, P]`` with ``P`` a protocol.
    """
    if get_origin(hint) is not Annotated:
        return None
    inner, *metadata = get_args(hint)
    if not any(isinstance(marker, Devices) for marker in metadata):
        return None
    args = get_args(inner)
    protocol = protocol_of(args[1]) if len(args) == 2 else None
    if get_origin(inner) is not Mapping or args[0] is not str or protocol is None:
        raise TypeError(
            f"{hint} is marked with Devices() but is not a 'Mapping[str, P]' with "
            "P a protocol. Write 'DevicesOf[P]'."
        )
    return protocol


def satisfying(components: Mapping[str, object], protocol: TypeForm[P]) -> dict[str, P]:
    """Return the components of *components* that satisfy *protocol*, by name."""
    return {
        name: component
        for name, component in components.items()
        if satisfies(component, protocol)
    }


def rejected(components: Mapping[str, Any], protocol: type) -> dict[str, list[str]]:
    """Return why each component that nearly matched *protocol* was left out.

    Only components carrying some of the protocol's members appear, so a
    component missing all of them does not drown out a near miss.
    """
    wanted = members(protocol)
    near: dict[str, list[str]] = {}
    for name, component in components.items():
        reasons = problems(component, protocol)
        if reasons and any(hasattr(component, member) for member in wanted):
            near[name] = reasons
    return near
