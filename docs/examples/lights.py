"""A session switching and dimming two lights with the built-in light stack."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003
from typing import TYPE_CHECKING, Any, ClassVar

from ophyd_async.core import (
    SignalRW,
    SoftSignalBackend,
    StandardReadable,
    StandardReadableFormat,
    soft_signal_rw,
)

from redsun import AsDevice, AsPresenter, AsView, Link, links_between
from redsun.presenter import LightPresenter  # noqa: TC001
from redsun.qt import QtSession
from redsun.view.qt.builtins import LightView  # noqa: TC001

if TYPE_CHECKING:
    from event_model import DataKey


# --8<-- [start:device]
class LimitedBackend(SoftSignalBackend[float]):
    """Keeps a value in memory and reports limits, as a hardware record does."""

    async def get_datakey(self, source: str) -> DataKey:
        key = await super().get_datakey(source)
        key["limits"] = {"control": {"low": 0.0, "high": 50.0}}
        return key


class MyLaser(StandardReadable):
    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.enabled = soft_signal_rw(bool, False)
            self.intensity = SignalRW(
                LimitedBackend(float, 10.0, units="mW", precision=1)
            )
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.wavelength = soft_signal_rw(int, 488, units="nm")
        super().__init__(name=name)


class MyLed(StandardReadable):
    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.enabled = soft_signal_rw(bool, True)
        super().__init__(name=name)


# --8<-- [end:device]
# --8<-- [start:session]
class MyApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "my-lab"}

    laser: AsDevice[MyLaser]
    led: AsDevice[MyLed]
    lights: AsPresenter[LightPresenter]
    lights_view: AsView[LightView]

    def wire(self) -> Iterator[Link]:
        # --8<-- [start:wire]
        yield from links_between(self.lights_view, self.lights)
        # --8<-- [end:wire]


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
