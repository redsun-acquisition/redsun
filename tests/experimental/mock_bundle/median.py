"""A presenter owning a plan that only runs with its own callback watching."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from event_model import DocumentRouter

from redsun.experimental import PlanEntry


class MockMedianPresenter(DocumentRouter):
    """Presenter offering the plan it filters, and filtering it itself."""

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name
        self.documents: list[str] = []

    def plan_map(self) -> Mapping[str, PlanEntry]:
        """Offer the median scan, which this presenter has to see."""
        return {"median_scan": {"plan": self.median_scan, "callbacks": [self]}}

    def median_scan(self) -> MsgGenerator[None]:
        """Open and close a run."""
        yield from bps.open_run()
        yield from bps.close_run()

    def __call__(
        self, name: str, doc: dict[Any, Any], validate: bool = False
    ) -> tuple[str, dict[Any, Any]]:
        self.documents.append(name)
        return super().__call__(name, doc, validate)

    def clear(self) -> None:
        """Forget every document seen."""
        self.documents.clear()
