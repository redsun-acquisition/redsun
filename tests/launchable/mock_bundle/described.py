"""Components whose constructors exercise each rule of describing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from annotated_types import Gt
from ophyd_async.core import Device
from pydantic import BaseModel, Field

from redsun import DeviceMapping

if TYPE_CHECKING:
    from decimal import Decimal as Unavailable

SENTINEL = object()
"""A default `pydantic` cannot write as JSON."""


class Calibration(BaseModel):
    """A value a provider could share."""

    offset: float
    """How far readings are shifted."""


class DescribedPresenter:
    """A presenter asking for one parameter of each kind describing sorts."""

    def __init__(
        self,
        scale: float = 1.0,
        /,
        name: str = "",
        *,
        step: Annotated[
            float,
            Gt(0),
            Field(
                title="Step",
                description="How far one press moves.",
                json_schema_extra={"unit": "um"},
            ),
        ] = 1.0,
        mode: Literal["fast", "fine"] = "fine",
        calibration: Calibration,
        devices: DeviceMapping,
        marker: object = SENTINEL,
        missing: Unavailable,
    ) -> None:
        self.name = name


class PrefixedDevice(Device):
    """A device whose prefix may come from a service."""

    def __init__(self, prefix: str, name: str = "") -> None:
        self.prefix = prefix
        super().__init__(name=name)
