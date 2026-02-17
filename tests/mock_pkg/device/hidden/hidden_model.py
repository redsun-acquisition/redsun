from typing import Any

from attrs import define
from sunflare.device import Device


@define(kw_only=True)
class HiddenModel(Device):
    """Hidden model for testing nested module discovery."""

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        super().__init__(name)
        self.__attrs_init__(**kwargs)

    def read_configuration(self) -> dict[str, Any]:
        raise NotImplementedError()

    def describe_configuration(self) -> dict[str, Any]:
        raise NotImplementedError()

    @property
    def parent(self) -> None:
        return None
