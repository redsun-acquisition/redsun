"""Build, use and close a session with no toolkit, then ask for one that is missing.

Run as a script by ``test_headless``, in an interpreter where the Qt packages
cannot be imported.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from ophyd_async.core import StandardReadable, StandardReadableFormat, soft_signal_rw
from psygnal import Signal

from redsun import AsDevice, AsPresenter, DeviceMapping, Session, slot

if TYPE_CHECKING:
    from collections.abc import Iterator

    from redsun import Link


class Stage(StandardReadable):
    def __init__(self, name: str, axis: str = "X") -> None:
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.axis = soft_signal_rw(str, initial_value=axis)
        super().__init__(name=name)


class Mover:
    sig_moved = Signal(str, float)

    def __init__(self, name: str, *, devices: DeviceMapping) -> None:
        self.name = name
        self.devices = devices


class Recorder:
    def __init__(self, name: str) -> None:
        self.name = name
        self.seen: list[tuple[str, float]] = []

    @slot
    def record(self, axis: str, amount: float) -> None:
        self.seen.append((axis, amount))


class Headless(Session):
    stage: AsDevice[Stage]
    mover: AsPresenter[Mover]
    recorder: AsPresenter[Recorder]

    def wire(self) -> Iterator[Link]:
        yield self.mover.sig_moved, self.recorder.record


def main() -> None:
    app = Headless([{"session": "lab"}, {"metadata": {"operator": "someone"}}]).build()
    assert set(app.devices) == {"stage"}
    assert set(app.presenters) == {"mover", "recorder"}
    assert dict(app.views) == {}

    app.mover.sig_moved.emit("X", 2.0)
    assert app.recorder.seen == [("X", 2.0)]

    app.shutdown()
    assert not app.is_built

    try:
        Session.from_config({"session": "lab", "frontend": "qt"})
    except ImportError as e:
        print(e)
    else:
        raise AssertionError("a frontend that cannot be imported was accepted")

    toolkit = {"qtpy", "PyQt6", "PySide6", "app_model", "magicgui"}
    loaded = sorted(name for name in toolkit if sys.modules.get(name) is not None)
    assert not loaded, loaded


if __name__ == "__main__":
    main()
