from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping
from typing import TYPE_CHECKING, TypeVar

from ophyd_async.core import Device

if TYPE_CHECKING:
    from ophyd_async.core import DeviceConnector

DeviceT = TypeVar("DeviceT", bound=Device)


class DeviceMap(MutableMapping[str, DeviceT], Device):
    """A dictionary of device children with string keys.

    Equivalent to [`DeviceVector`][ophyd_async.core.DeviceVector]
    but with string keys instead of integer indices.
    """

    def __init__(
        self,
        children: Mapping[str, DeviceT] | None = None,
        name: str = "",
        connector: DeviceConnector | None = None,
    ) -> None:
        self._children: dict[str, DeviceT] = children if children is not None else {}
        super().__init__(name, connector)

    def __getitem__(self, key: str) -> DeviceT:
        return super().__getitem__(key)

    def __setitem__(self, key: str, value: DeviceT) -> None:
        # Check the types on entry to dict to make sure we can't accidentally
        # make a non-integer named child
        if not isinstance(key, str):
            msg = f"Expected str, got {type(key)}"
            raise TypeError(msg)
        if not isinstance(value, Device):
            msg = f"Expected Device, got {value}"
            raise TypeError(msg)
        self._children[key] = value
        value.parent = self

    def __delitem__(self, key: int) -> None:
        del self._children[key]

    def __iter__(self) -> Iterator[int]:
        yield from self._children

    def __len__(self) -> int:
        return len(self._children)

    def children(self) -> Iterator[tuple[str, Device]]:
        for key, child in self._children.items():
            yield str(key), child
        yield from super().children()

    def __hash__(self) -> int:
        return hash(id(self))
