"""A presenter running every plan the session offers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator

from redsun.engine import RunEngine
from redsun.experimental import HasPlans, PlanEntry, Requires, slot

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from concurrent.futures import Future

    from redsun.experimental import CallbackType


class MockAcquisitionPresenter:
    """Presenter offering one plan and running every plan the session offers.

    It names no other component: the plans arrive from whatever satisfies
    `HasPlans`, each carrying the callbacks it requires.
    """

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.engine = RunEngine()
        self.entries: dict[str, PlanEntry] = {"stream": {"plan": self.stream}}
        self.subscribed: list[CallbackType] = []
        self.frames = 0
        self.run: Future[Any] | None = None
        self._tokens: list[int] = []

    def setup(self, sources: Requires[HasPlans]) -> None:
        """Collect the plans every other component offering them holds."""
        for source in sources.values():
            if source is self:
                continue
            for plan, entry in source.plan_map().items():
                if plan in self.entries:
                    raise ValueError(f"two components offer a plan called {plan!r}")
                self.entries[plan] = entry

    def plan_map(self) -> Mapping[str, PlanEntry]:
        """Offer the plan this presenter owns, not the ones it collected."""
        return {"stream": self.entries["stream"]}

    def stream(self, frames: int = 1) -> MsgGenerator[None]:
        """Open and close a run, recording how many frames it was asked for."""
        self.frames = frames
        yield from bps.open_run()
        yield from bps.close_run()

    @slot
    def launch(
        self,
        plan: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        attached: Sequence[CallbackType],
    ) -> None:
        """Run *plan* with the callbacks it requires, then the attached ones."""
        entry = self.entries[plan]
        own = list(entry.get("callbacks", ()))
        chosen = own
        if entry.get("extendable", True):
            chosen = own + [cb for cb in attached if all(cb is not o for o in own)]
        self.subscribed = chosen
        self._tokens = [self.engine.subscribe(cb) for cb in chosen]
        self.run = self.engine(entry["plan"](*args, **kwargs))
        self.run.add_done_callback(self._release)

    def _release(self, run: Future[Any]) -> None:
        for token in self._tokens:
            self.engine.unsubscribe(token)
        self._tokens.clear()
