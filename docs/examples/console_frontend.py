"""The frontend of the guide "How to write a frontend"."""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping  # noqa: TC003
from dataclasses import dataclass
from typing import ClassVar

import psygnal
from bluesky.protocols import Reading  # noqa: TC002
from ophyd_async.core import StandardReadable, soft_signal_rw

from redsun import AsDevice, AsView, Frontend, Link, Placement, Session, slot
from redsun.ports import SlotThread  # noqa: TC001


# --8<-- [start:placement]
@dataclass(frozen=True)
class Line(Placement):
    order: int = 0


class ConsoleView:
    def text(self) -> str:
        raise NotImplementedError


# --8<-- [end:placement]
# --8<-- [start:frontend]
class Console(Frontend):
    requires: ClassVar[Mapping[type[Placement], type]] = {Line: ConsoleView}

    @classmethod
    def thread_of(cls, consumer: object) -> SlotThread:
        return "main" if isinstance(consumer, ConsoleView) else None


# --8<-- [end:frontend]
# --8<-- [start:session]
class ConsoleSession(Session):
    frontend = Console

    def present(self) -> None:
        views = [v for v in self.views.values() if isinstance(v, ConsoleView)]
        self.lines = sorted(views, key=self.order_of)

    @staticmethod
    def order_of(view: ConsoleView) -> int:
        placement = getattr(view, "placement", None)
        return placement.order if isinstance(placement, Line) else 0

    def run(self, interval: float = 0.5) -> None:
        self.build()
        try:
            while True:
                psygnal.emit_queued()
                print(" | ".join(view.text() for view in self.lines), flush=True)
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()


# --8<-- [end:session]
class MyStage(StandardReadable):
    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float)
        super().__init__(name=name)


# --8<-- [start:view]
class PositionLine(ConsoleView):
    placement: Placement = Line(order=0)

    def __init__(self, name: str) -> None:
        self.name = name
        self.position = 0.0

    @slot
    def show_reading(self, reading: dict[str, Reading[float]]) -> None:
        for entry in reading.values():
            self.position = entry["value"]

    def text(self) -> str:
        return f"{self.name}: {self.position:.2f}"


# --8<-- [end:view]
# --8<-- [start:app]
class MyApp(ConsoleSession):
    stage: AsDevice[MyStage]
    position: AsView[PositionLine]

    def wire(self) -> Iterator[Link]:
        yield self.stage.position, self.position.show_reading


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:app]
