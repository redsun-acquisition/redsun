"""A presenter running the plans the components of a session offer."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence  # noqa: TC003
from dataclasses import KW_ONLY, dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from bluesky.utils import RequestAbort, RequestStop, RunEngineInterrupted
from psygnal import Signal

from redsun.engine import Deferrals, RunEngine
from redsun.injection import provides
from redsun.log import Loggable
from redsun.path_provider import SessionPathProvider  # noqa: TC001
from redsun.ports import slot
from redsun.presenter.plan_spec import (
    PlanSpec,
    UnresolvableAnnotationError,
    collect_arguments,
    create_plan_spec,
    resolve_arguments,
)
from redsun.registry import (
    CallbackType,
    DeviceMapping,
    HasActions,
    HasPlans,
)

if TYPE_CHECKING:
    from concurrent.futures import Future
    from pathlib import Path

    from redsun.registry import PlanEntry


@runtime_checkable
class DescribesPlans(Protocol):
    """A component describing the plans it runs."""

    @property
    def plans(self) -> Mapping[str, PlanSpec]:
        """The specification of each plan, by name."""
        ...

    @property
    def callbacks(self) -> Mapping[str, CallbackType]:
        """The document callbacks a user may attach to a run, by name."""
        ...

    @property
    def plan_callbacks(self) -> Mapping[str, Sequence[CallbackType]]:
        """The document callbacks each plan runs with, by plan name."""
        ...


class AbortFilter(logging.Filter):
    """Drop the record `bluesky` logs for an abort the presenter asked for."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Keep every record but one carrying a `RequestAbort`."""
        return not (record.exc_info and isinstance(record.exc_info[1], RequestAbort))


@dataclass(eq=False)
class AcquisitionPresenter(Loggable):
    """Run the plans the components of a session offer, one at a time.

    The plans of every component with a `plan_map` are gathered in `setup`;
    one whose signature no plan widget can show is left out with a warning.
    A run gets the callbacks its plan lists, then those attached to it. Its
    files are named after the plan while it runs. Its end is reported on
    `sig_plan_done`, or, when it raises, on `sig_plan_failed` with the error
    logged.
    """

    sig_plan_started = Signal(str)
    """Plan, as it is handed to the engine."""

    sig_plan_done = Signal(str)
    """Plan, once it has finished or been stopped."""

    sig_plan_failed = Signal(str, str)
    """Plan, and why it failed."""

    sig_progress = Signal(tuple)
    """Every progress scope of the running plan, as the engine reports them."""

    sig_locks_changed = Signal(frozenset)
    """Names of the devices the running plan holds, whenever they change."""

    sig_action_changed = Signal(str, object)
    """Action and its state, from the actions of every component."""

    sig_base_dir_changed = Signal(object)
    """The directory runs now write under."""

    name: str
    """Name of the presenter in its session."""

    _: KW_ONLY

    devices: DeviceMapping = field(repr=False)
    """Devices of the session, which plan arguments name."""

    def __post_init__(self) -> None:
        self._engine = RunEngine()
        self._deferrals = Deferrals(self._engine)
        self._engine.sig_locks_changed.connect(self.sig_locks_changed.emit)
        self._engine.sig_progress.connect(self.sig_progress.emit)
        self._entries: dict[str, PlanEntry] = {}
        self._specs: dict[str, PlanSpec] = {}
        self._callbacks: dict[str, CallbackType] = {}
        self._action_owners: dict[str, HasActions] = {}
        self._paths: SessionPathProvider | None = None
        self._futures: set[Future[Any]] = set()
        self._running: str | None = None
        self._error: BaseException | None = None

    @provides
    def engine(self) -> RunEngine:
        """Return the engine every plan runs on, shared with any component asking for one."""
        return self._engine

    @provides
    def deferrals(self) -> Deferrals:
        """Return the deferrals of the engine, shared with any component asking for them."""
        return self._deferrals

    def setup(
        self,
        providers: Mapping[str, HasPlans],
        callbacks: Mapping[str, CallbackType],
        paths: SessionPathProvider,
    ) -> None:
        """Gather the plans of every provider, the callbacks, and the path provider."""
        for component in providers.values():
            for plan, entry in component.plan_map().items():
                try:
                    self._specs[plan] = create_plan_spec(entry["plan"], self.devices)
                except (UnresolvableAnnotationError, ValueError) as error:
                    self.logger.warning(f"Leaving out {plan!r}: {error}")
                    continue
                self._entries[plan] = entry
                if isinstance(component, HasActions):
                    self._action_owners[plan] = component
        for owner in {id(o): o for o in self._action_owners.values()}.values():
            owner.actions.sig_changed.connect(self.sig_action_changed.emit)
        self._callbacks = dict(callbacks)
        self._paths = paths
        paths.sig_base_dir_changed.connect(self.sig_base_dir_changed.emit)

    @property
    def plans(self) -> Mapping[str, PlanSpec]:
        """The specification of each plan, by name."""
        return self._specs

    @property
    def callbacks(self) -> Mapping[str, CallbackType]:
        """The document callbacks a user may attach to a run, by name."""
        return self._callbacks

    @property
    def plan_callbacks(self) -> Mapping[str, Sequence[CallbackType]]:
        """The document callbacks each plan runs with, by plan name."""
        return {
            plan: tuple(entry.get("callbacks", ()))
            for plan, entry in self._entries.items()
        }

    @slot
    def launch(
        self, plan: str, values: dict[str, Any], attached: Sequence[str] = ()
    ) -> None:
        """Run *plan* with the parameter *values*, attaching the callbacks named.

        Refused, with a warning, while another plan runs. Values that cannot
        be turned into the plan's arguments are reported on `sig_plan_failed`.
        """
        if self._futures or self._engine.state != "idle":
            self.logger.warning(f"A plan is running; {plan!r} not launched")
            return
        entry, spec = self._entries[plan], self._specs[plan]
        try:
            self._check_devices(spec, values)
            args, kwargs = collect_arguments(
                spec, resolve_arguments(spec, values, self.devices)
            )
            # a DocumentRouter is callable as (name, doc), but not typed as bluesky asks
            subs: list[Any] = [
                *entry.get("callbacks", ()),
                *(self._callbacks[name] for name in attached),
            ]
        except Exception as error:
            self.logger.exception(f"Launching {plan!r} failed")
            self.sig_plan_failed.emit(plan, str(error) or type(error).__name__)
            return
        if self._paths is not None:
            self._paths.set_plan(plan)
        self._running = plan
        self.logger.info(f"Launching {plan!r}")
        # before the engine has it, so a plan ending at once is still seen to start
        self.sig_plan_started.emit(plan)
        self._track(self._engine(entry["plan"](*args, **kwargs), subs))

    @slot
    def pause(self) -> None:
        """Pause the running plan at its next checkpoint."""
        self._engine.request_pause(defer=True)

    @slot
    def resume(self) -> None:
        """Resume the paused plan."""
        self._track(self._engine.resume())

    @slot
    def stop(self) -> None:
        """Stop the running or paused plan, which ends as done."""
        if self._engine.state == "idle":
            self.logger.debug("No plan to stop")
            return
        self.logger.info(f"Stopping {self._running!r}")
        self._track(self._engine.stop())

    @slot
    def request_action(self, action: str, on: bool) -> None:
        """Ask for *action* of the running plan, or ask it to end."""
        owner = self._action_owners.get(self._running or "")
        if owner is None:
            self.logger.warning(f"Action {action!r} refused: no running plan offers it")
            return
        owner.actions.request(action, on)

    @slot
    def set_base_dir(self, path: Path) -> None:
        """Make runs write under *path*."""
        if self._paths is None:
            return
        try:
            self._paths.set_base_dir(path)
        except RuntimeError as error:
            self.logger.warning(f"Keeping the base directory: {error}")

    def shutdown(self) -> None:
        """Abort a running or paused plan, reporting neither its end nor a failure."""
        if not self._futures and self._engine.state != "paused":
            return
        bluesky_log = logging.getLogger("bluesky")
        abort_filter = AbortFilter()
        bluesky_log.addFilter(abort_filter)
        try:
            with self.sig_plan_done.blocked(), self.sig_plan_failed.blocked():
                self._engine.abort().result(timeout=10)
        finally:
            bluesky_log.removeFilter(abort_filter)

    def _check_devices(self, spec: PlanSpec, values: Mapping[str, Any]) -> None:
        for parameter in spec.parameters:
            if parameter.device_proto is None or parameter.name not in values:
                continue
            value = values[parameter.name]
            names = [value] if isinstance(value, str) else [str(v) for v in value]
            missing = [name for name in names if name not in self.devices]
            if missing:
                raise ValueError(f"no device named {', '.join(missing)}")

    def _track(self, future: Future[Any]) -> None:
        self._futures.add(future)
        future.add_done_callback(self._on_future_done)

    def _on_future_done(self, future: Future[Any]) -> None:
        self._futures.discard(future)
        error = future.exception()
        # a pause or a stop also ends the run's future with an interruption
        if error is not None and not isinstance(
            error, (RunEngineInterrupted, RequestStop, RequestAbort)
        ):
            self._error = error
        # a paused plan has not ended: resuming makes a new future
        if self._futures or self._engine.state == "paused":
            return
        plan, self._running = self._running or "", None
        failure, self._error = self._error, None
        if self._paths is not None:
            self._paths.reset_plan()
        if failure is None:
            self.logger.info(f"{plan!r} ended")
            self.sig_plan_done.emit(plan)
        else:
            self.logger.error(f"{plan!r} failed", exc_info=failure)
            self.sig_plan_failed.emit(plan, str(failure) or type(failure).__name__)
