from __future__ import annotations

import asyncio
from concurrent.futures import Future
from functools import partial
from threading import Lock, Thread
from typing import TYPE_CHECKING, Any, TypeVar

from bluesky.run_engine import (
    RunEngine as BlueskyRunEngine,
)
from bluesky.run_engine import RunEngineResult
from bluesky.utils import IllegalMessageSequence
from psygnal import Signal

from redsun.aio import get_shared_loop

from ._progress import PlanProgress, ProgressState, depth, empty_state, snapshot

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Mapping
    from typing import Literal, TypeAlias

    from bluesky.utils import Msg, Subscribers

    from redsun.engine.actions import SRLatch

    Preprocessor: TypeAlias = Callable[
        [Iterable[Msg], Callable[[Msg], Msg | None]], Iterable[Msg]
    ]
    MDValidator: TypeAlias = Callable[[dict[str, Any]], None]
    MDNormalizer: TypeAlias = Callable[[dict[str, Any]], dict[str, Any]]
    MDScanIDSource: TypeAlias = Callable[[dict[str, Any]], int | Awaitable[int]]


def default_scan_id_source(md: dict[str, Any]) -> int:
    scan_id: int = md.get("scan_id", 0)
    return scan_id + 1


__all__ = ["RunEngine", "RunEngineResult", "register_bound_command"]

R = TypeVar("R")


class RunEngine(BlueskyRunEngine):
    """Runs plans and emits documents without blocking the calling thread.

    Wraps `bluesky.run_engine.RunEngine`: `__call__` runs the plan on a
    separate thread and returns a concurrent.futures.Future of its result.

    Parameters
    ----------
    md
        Metadata store, a `dict` by default. Any object with `__getitem__`,
        `__setitem__` and `clear` works, such as historydict.HistoryDict,
        which persists history in a sqlite file.

    loop: asyncio.AbstractEventLoop, optional
        Event loop plans run on. Defaults to the shared background loop.

    preprocessors
        Generator functions modifying a plan's messages, such as the
        `bluesky.plans` functions ending in 'wrapper'. `[f, g]` applies as
        `f(g(plan))`.

    md_validator
        Raises to prevent a run whose metadata it finds invalid; its return
        value is ignored.

    md_normalizer
        Like md_validator, raises for invalid metadata; otherwise returns the
        normalized metadata.

    scan_id_source
        Function, possibly async, returning the next scan_id. By default
        scan_id increments by 1.

    call_returns_result
        What the Future `__call__` returns holds: a `RunEngineResult`
        describing the run if `True`, a tuple of uids if `False`.


    Attributes
    ----------
    md
        The metadata store described above.

    record_interruptions
        False by default. True adds an event stream recording interruptions
        (pauses, suspensions).

    state
        One of `idle`, `running`, `pausing`, `paused`, `halting`,
        `stopping`, `aborting`, `suspending` and `panicked`.

    suspenders
        Read-only collection of `bluesky.suspenders.SuspenderBase` objects
        that suspend and resume execution.

    preprocessors : list
        The preprocessors described above.

    msg_hook
        `f(msg)` called with every `bluesky.Msg` before it is processed,
        for logging or debugging. None by default.

    state_hook
        `f(new_state, old_state)` called on every state change. None by
        default.

    waiting_hook
        `f(status_object)` called while waiting for long-running commands
        (trigger, set, kickoff, complete), for example to show progress.

    progress_hook
        `f(scopes)` called with the open progress scopes of the running plan,
        parents first, or `None` to clear them. The engine sets its own, which
        feeds `sig_progress`.

    ignore_callback_exceptions
        Boolean, False by default.

    loop : asyncio event loop
        e.g., `asyncio.get_event_loop()` or `asyncio.new_event_loop()`

    max_depth
        Maximum stack depth, preventing calls to the RunEngine from inside a
        function, which breaks introspection. None by default; 2 suits the
        Python interpreter and 11 `IPython` (tested on 5.1.0).

    pause_msg : str
        Message printed when a run is interrupted, with instructions for
        changing the RunEngine's state. `bluesky.run_engine.PAUSE_MSG` by
        default.

    commands:
        The list of commands available to Msg.

    """

    sig_locks_changed = Signal(frozenset)
    """The names of the locked devices, whenever that set changes."""

    sig_state_changed = Signal(str, str)
    """The engine's new and old state on every change, named as `state` names them."""

    sig_progress = Signal(tuple)
    """Every progress scope of the running plan, as a tuple of `ProgressState`,
    parents before children, whenever one is declared, updated or finished;
    an empty tuple when none is left."""

    # a resumed plan replays its messages since the last checkpoint, and a
    # declaration replayed while its scope is still open would be refused
    _UNCACHEABLE_COMMANDS = [  # noqa: RUF012
        *BlueskyRunEngine._UNCACHEABLE_COMMANDS,
        "declare_progress",
        "update_progress",
    ]

    def __init__(
        self,
        md: dict[str, Any] | None = None,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        preprocessors: list[Preprocessor] | None = None,
        md_validator: MDValidator | None = None,
        md_normalizer: MDNormalizer | None = None,
        scan_id_source: MDScanIDSource | None = default_scan_id_source,
        call_returns_result: bool = True,
    ):
        # set before bluesky's constructor, which already moves the state to idle
        # each lock's devices by token, so a lock replayed after a rewind
        # replaces its own entry instead of adding another
        self._held: dict[str, frozenset[str]] = {}
        # plans lock devices on the engine's thread, views read on the main one
        self._held_guard = Lock()
        self._progress_scopes: dict[str, PlanProgress] = {}
        self._progress_listed: tuple[PlanProgress, ...] = ()
        self._progress_states: dict[PlanProgress, ProgressState] = {}
        self._progress_hook_active = False
        self._progress_shown = False
        self._progress_closing = False
        super().__init__(
            md=md,
            loop=loop or get_shared_loop(),
            preprocessors=preprocessors,
            md_validator=md_validator,
            md_normalizer=md_normalizer,
            scan_id_source=scan_id_source,  # type: ignore[arg-type]
            call_returns_result=call_returns_result,
            # bluesky's default installs a SIGINT handler, which only the main
            # thread may do, and plans run on a thread of their own
            context_managers=[],
        )

        # override pause message to be an empty string
        self.pause_msg = ""
        # bluesky types the hook as None, its default
        self.state_hook = self._on_state_change  # type: ignore[assignment]
        self.progress_hook: Callable[[list[PlanProgress] | None], None] | None = (
            self._report_scopes
        )

        # register custom commands
        self._command_registry.update(
            {
                "wait_for_actions": self._wait_for_actions,
                "lock": self._lock,
                "unlock": self._unlock,
                "declare_progress": self._declare_progress,
                "update_progress": self._update_progress,
            }
        )

    @property
    def locked(self) -> frozenset[str]:
        """The names of the devices the running plan locks."""
        with self._held_guard:
            return frozenset().union(*self._held.values())

    def __call__(  # type: ignore[override]
        self,
        plan: Iterable[Msg],
        subs: Subscribers | None = None,
        /,
        **metadata_kw: Any,
    ) -> Future[RunEngineResult | tuple[str, ...]]:
        """Execute a plan.

        Keyword arguments are metadata recorded with every run the plan
        creates. The plan and optional subscriptions are positional.

        Parameters
        ----------
        plan
            A generator yielding `Msg` objects, or an iterable returning one.
        subs
            Callbacks subscribed for this run only, given as:

            * a callable, which will be subscribed to 'all'
            * a list of callables, which again will be subscribed to 'all'
            * a dictionary, mapping specific subscriptions to callables or
              lists of callables; valid keys are {'all', 'start', 'stop',
              'event', 'descriptor'}
        """
        return self._run_in_thread(partial(super().__call__, plan, subs, **metadata_kw))

    def resume(self) -> Future[RunEngineResult | tuple[str, ...]]:
        """Resume the paused plan on a separate thread.

        Returns a future of the resumed plan's result. Pausing completes the
        future `__call__` returned, so this is a new one.
        """
        return self._run_in_thread(super().resume)

    def stop(self) -> Future[RunEngineResult | tuple[str, ...]]:
        """Stop the plan and mark it successful, on a thread of its own.

        A paused plan runs its cleanup there, not on the caller's thread.
        """
        return self._run_in_thread(super().stop)

    def abort(self, reason: str = "") -> Future[RunEngineResult | tuple[str, ...]]:
        """Stop the plan and mark it aborted, on a thread of its own."""
        return self._run_in_thread(partial(super().abort, reason))

    def halt(self) -> Future[RunEngineResult | tuple[str, ...]]:
        """Stop the plan with no cleanup, on a thread of its own."""
        return self._run_in_thread(super().halt)

    def _run_in_thread(self, call: Callable[[], R]) -> Future[R]:
        """Run *call* on a thread of its own, which ends with it, and return its future."""
        future: Future[R] = Future()

        def run() -> None:
            if not future.set_running_or_notify_cancel():
                return
            try:
                future.set_result(call())
            except BaseException as e:  # noqa: BLE001 - the future carries whatever the plan raised
                future.set_exception(e)

        Thread(target=run, name="RunEngine", daemon=True).start()
        return future

    async def _lock(self, msg: Msg) -> None:
        self._update_locks(msg.kwargs["token"], {device.name for device in msg.args})

    async def _unlock(self, msg: Msg) -> None:
        self._update_locks(msg.kwargs["token"], None)

    def _on_state_change(self, new: str, old: str) -> None:
        """Announce the state, releasing every lock on idle first.

        A halted plan skips its cleanup, so its `unlock` messages never run.
        """
        if new == "idle":
            self._release_locks()
            self._close_progress()
        self.sig_state_changed.emit(new, old)

    async def _declare_progress(self, msg: Msg) -> PlanProgress:
        """Open the progress scope a `declare_progress` message names.

        Raises
        ------
        IllegalMessageSequence
            If the scope is already open, or its parent is not.
        """
        name = msg.kwargs["name"]
        if name in self._progress_scopes:
            raise IllegalMessageSequence(
                f"A progress scope named {name!r} is already open."
            )
        parent_name = msg.kwargs.get("parent")
        parent = None
        if parent_name is not None:
            parent = self._progress_scopes.get(parent_name)
            if parent is None:
                raise IllegalMessageSequence(
                    f"Parent progress scope {parent_name!r} does not exist. "
                    "It must be declared before its children."
                )
        scope = PlanProgress(name, parent=parent)
        self._progress_scopes[name] = scope
        self._rebuild_progress_hook()
        return scope

    async def _update_progress(self, msg: Msg) -> None:
        """Update, or finish with `done=True`, the scope an `update_progress` names.

        Raises
        ------
        IllegalMessageSequence
            If no scope of that name is open.
        """
        name = msg.kwargs["name"]
        scope = self._progress_scopes.get(name)
        if scope is None:
            raise IllegalMessageSequence(
                f"No progress scope named {name!r} is open. "
                "Use 'declare_progress' first."
            )
        if msg.kwargs.get("done", False):
            scope.finish()
            del self._progress_scopes[name]
            self._rebuild_progress_hook()
            return
        scope._notify(
            current=msg.kwargs.get("current"),
            initial=msg.kwargs.get("initial"),
            target=msg.kwargs.get("target"),
            unit=msg.kwargs.get("unit", "unit"),
            precision=msg.kwargs.get("precision"),
            fraction=msg.kwargs.get("fraction"),
            time_elapsed=msg.kwargs.get("time_elapsed"),
            time_remaining=msg.kwargs.get("time_remaining"),
        )

    def _rebuild_progress_hook(self) -> None:
        """Hand `progress_hook` the open scopes, parents first, clearing it before."""
        if self.progress_hook is None:
            return
        active = sorted(
            (scope for scope in self._progress_scopes.values() if not scope.done),
            key=depth,
        )
        if self._progress_hook_active:
            self.progress_hook(None)
        self._progress_hook_active = bool(active)
        if active:
            self.progress_hook(active)

    def _report_scopes(self, scopes: list[PlanProgress] | None) -> None:
        """Follow the scopes the engine lists, and announce them."""
        self._progress_listed = tuple(scopes or ())
        for scope in self._progress_listed:
            if scope not in self._progress_states:
                self._progress_states[scope] = empty_state(scope)
                scope.watch(partial(self._on_progress_update, scope))
        self._announce_progress()

    def _on_progress_update(self, scope: PlanProgress, **update: Any) -> None:
        self._progress_states[scope] = snapshot(scope, update)
        self._announce_progress()

    def _announce_progress(self) -> None:
        if self._progress_closing:
            return
        states = tuple(self._progress_states[scope] for scope in self._progress_listed)
        self._progress_shown = bool(states)
        self.sig_progress.emit(states)

    def _close_progress(self) -> None:
        """Finish every scope a plan left open, and announce that none is left."""
        self._progress_closing = True
        try:
            for scope in self._progress_scopes.values():
                if not scope.done:
                    scope.finish()
        finally:
            self._progress_closing = False
        self._progress_scopes.clear()
        self._progress_states.clear()
        self._progress_listed = ()
        self._progress_hook_active = False
        if self._progress_shown:
            self._progress_shown = False
            self.sig_progress.emit(())

    def _release_locks(self) -> None:
        with self._held_guard:
            held = bool(self._held)
            self._held.clear()
        if held:
            self.sig_locks_changed.emit(frozenset())

    def _update_locks(self, token: str, names: set[str] | None) -> None:
        """Hold *names* under *token*, or release the token when *names* is None."""
        with self._held_guard:
            before = frozenset().union(*self._held.values())
            if names is None:
                self._held.pop(token, None)
            else:
                self._held[token] = frozenset(names)
            after = frozenset().union(*self._held.values())
        if after != before:
            self.sig_locks_changed.emit(after)

    async def _wait_for_actions(self, msg: Msg) -> tuple[str, SRLatch] | None:
        """Wait for any of the given latches to be set or reset, and return it.

        Returns the name and latch in the wanted state, the one that reached it
        first of several, or `None` if none did within the interval.

        Parameters
        ----------
        msg
            Carries a map of SRLatch in `msg.args`, and in `msg.kwargs` how
            long to wait and for which state:

            Msg("wait_for_actions", None, latches, poll_interval=0.1, wait_for="set")
        """
        latch_map: Mapping[str, SRLatch] = msg.args[0]
        interval: float | None = msg.kwargs.get("poll_interval", None)
        wait_for: Literal["set", "reset"] = msg.kwargs.get("wait_for", "set")

        # Create a mapping to track which task corresponds to which latch
        if wait_for == "set":
            latch_tasks = {
                asyncio.create_task(latch.wait_for_set(), name=name)
                for name, latch in latch_map.items()
            }
        else:
            latch_tasks = {
                asyncio.create_task(latch.wait_for_reset(), name=name)
                for name, latch in latch_map.items()
            }

        try:
            done, _ = await asyncio.wait(
                latch_tasks, return_when=asyncio.FIRST_COMPLETED, timeout=interval
            )
        finally:
            # a plan stopped while it waits cancels this coroutine, and the
            # tasks would outlive it
            for task in latch_tasks:
                task.cancel()

        ready = {task.get_name() for task in done}
        if not ready:
            return None
        # min keeps the first of equals, so latches that changed together
        # are told apart by their order in the map
        first = min(
            (name for name in latch_map if name in ready),
            key=lambda name: latch_map[name].changed_at,
        )
        return first, latch_map[first]


def register_bound_command(
    engine: RunEngine,
    command: Callable[[RunEngine, Msg], Any],
) -> None:
    """Register a custom command in the given run engine.

    Unlike `RunEngine.register_command`, binds the command to *engine*.

    Parameters
    ----------
    engine: RunEngine
        The run engine to register the command in.
    command: Callable[[RunEngine, Msg], Any]
        The command, taking a `RunEngine` and a `Msg`.
    """
    bound_command = partial(command, engine)
    command_name = command.__name__
    engine.register_command(command_name, bound_command)
