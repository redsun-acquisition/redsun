from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from psygnal import Signal

from redsun.experimental import (
    CallbackType,
    DeviceMapping,
    HasPlans,
    Placement,
    RequiresBuilt,
    Settings,
    slot,
)
from redsun.presenter.plan_spec import (
    collect_arguments,
    create_plan_spec,
    resolve_arguments,
)

from .keys import Absent, Readings


@dataclass(frozen=True)
class Somewhere(Placement):
    """Stand-in placement: the core ships none, and no frontend is named here."""


class MockMotorView:
    """View consuming a shared value, a framework object and an absent one."""

    sig_requested = Signal(str, float)
    placement: Placement = Somewhere()

    def __init__(
        self,
        name: str,
        /,
        callbacks: Mapping[str, CallbackType],
        readings: Readings,
        missing: Absent | None = None,
        title: str = "",
    ) -> None:
        self.name = name
        self.callbacks = callbacks
        self.readings = readings
        self.missing = missing
        self.title = title

    @slot
    def refresh(self, axis: str, amount: float) -> None:
        self.refreshed = (axis, amount)


class MockAcquisitionView:
    """View offering the session's plans, and remembering what a user attaches.

    Headless: it holds what a plan widget would show, and sends what a run
    button would.
    """

    sig_launch = Signal(str, object, object, object)
    placement: Placement = Somewhere()

    def __init__(
        self,
        name: str,
        /,
        sources: RequiresBuilt[HasPlans],
        devices: DeviceMapping,
        callbacks: Mapping[str, CallbackType],
        settings: Settings,
    ) -> None:
        self.name = name
        self.devices = devices
        self.callbacks = callbacks
        self.settings = settings
        self.entries = {
            plan: entry
            for source in sources.values()
            for plan, entry in source.plan_map().items()
        }
        self.specs = {
            plan: create_plan_spec(entry["plan"], devices)
            for plan, entry in self.entries.items()
        }

    def attached(self, plan: str) -> list[str]:
        """Return the callbacks attached to *plan*, or every one if none were."""
        remembered = self.settings.get("callbacks", {}).get(plan)
        if remembered is None:
            return list(self.callbacks)
        return [name for name in remembered if name in self.callbacks]

    def attach(self, plan: str, names: list[str]) -> None:
        """Remember *names* as the callbacks attached to *plan*."""
        remembered = dict(self.settings.get("callbacks", {}))
        remembered[plan] = names
        self.settings.set("callbacks", remembered)

    def request(self, plan: str, values: Mapping[str, Any] | None = None) -> None:
        """Ask for *plan* to run, with its arguments and attached callbacks."""
        spec = self.specs[plan]
        resolved = resolve_arguments(spec, dict(values or {}), self.devices)
        args, kwargs = collect_arguments(spec, resolved)
        self.sig_launch.emit(
            plan, args, kwargs, [self.callbacks[name] for name in self.attached(plan)]
        )
