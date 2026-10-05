"""A presenter running the plans the components of a session offer."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from concurrent.futures import wait
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

    @property
    def base_dir(self) -> Path | None:
        """The directory runs write under; `None` before it is known."""
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
    """Plan, once the engine has started it."""

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
        self._engine.sig_state_changed.connect(self._on_state_changed)
        self._entries: dict[str, PlanEntry] = {}
        self._specs: dict[str, PlanSpec] = {}
        self._callbacks: dict[str, CallbackType] = {}
        self._action_owners: dict[str, HasActions] = {}
        self._paths: SessionPathProvider | None = None
        self._futures: set[Future[Any]] = set()
        self._running: str | None = None
        self._error: BaseException | None = None
        self._closed = False
        self._on_start: Callable[[], None] | None = None

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
                except (UnresolvableAnnotationError, TypeError, ValueError) as error:
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

    @property
    def base_dir(self) -> Path | None:
        """The directory runs write under; `None` before `setup`."""
        return None if self._paths is None else self._paths.base_dir

    @slot
    def launch(
        self, plan: str, values: dict[str, Any], attached: Sequence[str] = ()
    ) -> None:
        """Run *plan* with the parameter *values*, attaching the callbacks named.

        Refused, with a warning, while another plan runs. Values that cannot
        be turned into the plan's arguments are reported on `sig_plan_failed`.
        """
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
        except ValueError as error:
            self.logger.warning(f"Not launching {plan!r}: {error}")
            self.sig_plan_failed.emit(plan, str(error))
            return
        except Exception as error:
            self.logger.exception(f"Launching {plan!r} failed")
            self.sig_plan_failed.emit(plan, str(error) or type(error).__name__)
            return
        if self._futures or self._engine.state != "idle":
            self.logger.warning(f"A plan is running; {plan!r} not launched")
            return
        if self._paths is not None:
            self._paths.set_plan(plan)
        self._running = plan
        self.logger.info(f"Launching {plan!r}")
        self._track(self._engine(entry["plan"](*args, **kwargs), subs))

    @slot
    def pause(self) -> None:
        """Pause the running plan at its next checkpoint."""
        if self._when_started(self.pause):
            return
        if self._engine.state != "running":
            self.logger.debug("No plan to pause")
            return
        try:
            self._engine.request_pause(defer=True)
        # bluesky's TransitionError, raised when the plan ended since the check
        except RuntimeError as error:
            self.logger.warning(f"Not pausing: {error}")

    @slot
    def resume(self) -> None:
        """Resume the paused plan, or withdraw a pause it has not reached yet."""
        if self._engine.state != "paused":
            self._engine.cancel_pause()
            return
        self._track(self._engine.resume())

    @slot
    def stop(self) -> None:
        """Stop the running or paused plan, which ends as done."""
        if self._when_started(self.stop, replace=True):
            return
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
        """Abort a running or paused plan, reporting neither its end nor a failure.

        Returns once the plan's cleanup has run, or after ten seconds.
        """
        self._closed = True
        if not self._futures and self._engine.state != "paused":
            return
        bluesky_log = logging.getLogger("bluesky")
        abort_filter = AbortFilter()
        bluesky_log.addFilter(abort_filter)
        try:
            # aborting a running plan only cancels it: its cleanup ends the run's future
            pending = [*self._futures, self._engine.abort()]
            wait(pending, timeout=10)
        finally:
            bluesky_log.removeFilter(abort_filter)

    def _check_devices(self, spec: PlanSpec, values: Mapping[str, Any]) -> None:
        for parameter in spec.parameters:
            if parameter.device_proto is None or parameter.name not in values:
                continue
            proto = parameter.device_proto
            value = values[parameter.name]
            many = isinstance(value, (Sequence, AbstractSet)) and not isinstance(
                value, str
            )
            for name in map(str, value if many else [value]):
                if name not in self.devices:
                    raise ValueError(f"no device named {name!r}")
                if not isinstance(self.devices[name], proto):
                    raise ValueError(f"{name!r} is not a {proto.__name__}")  # noqa: TRY004

    def _when_started(
        self, action: Callable[[], None], *, replace: bool = False
    ) -> bool:
        """Keep *action* for when the launched plan starts; whether it was kept."""
        if self._running is None or self._engine.state != "idle":
            return False
        if replace or self._on_start is None:
            self._on_start = action
        return True

    def _on_state_changed(self, new: str, old: str) -> None:
        if (old, new) != ("idle", "running"):
            return
        plan, action, self._on_start = self._running, self._on_start, None
        # a plan another component runs on the shared engine is not reported
        if plan is None:
            return
        self.sig_plan_started.emit(plan)
        if action is not None:
            # on the engine's thread, which a pause request would block
            threading.Thread(target=action, daemon=True).start()

    def _track(self, future: Future[Any]) -> None:
        self._futures.add(future)
        future.add_done_callback(self._on_future_done)

    def _on_future_done(self, future: Future[Any]) -> None:
        error = future.exception()
        self._futures.discard(future)
        if self._closed:
            return
        # a pause or a stop also ends the run's future with an interruption
        if error is not None and not isinstance(
            error, (RunEngineInterrupted, RequestStop, RequestAbort)
        ):
            self._error = error
        # a paused plan has not ended: resuming makes a new future
        if self._futures or self._engine.state == "paused":
            return
        plan, self._running, self._on_start = self._running, None, None
        failure, self._error = self._error, None
        # the other future of a stop has already reported the end
        if plan is None:
            return
        if self._paths is not None:
            self._paths.reset_plan()
        if failure is None:
            self.logger.info(f"{plan!r} ended")
            self.sig_plan_done.emit(plan)
        else:
            self.logger.error(f"{plan!r} failed", exc_info=failure)
            self.sig_plan_failed.emit(plan, str(failure) or type(failure).__name__)
