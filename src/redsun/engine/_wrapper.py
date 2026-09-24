from __future__ import annotations

import asyncio
from concurrent.futures import Future
from functools import partial
from threading import Lock, Thread
from typing import TYPE_CHECKING, Any, TypeVar

from bluesky.run_engine import (
    LoggingPropertyMachine,
    RunEngineResult,
    RunEngineStateMachine,
)
from bluesky.run_engine import (
    RunEngine as BlueskyRunEngine,
)
from psygnal import Signal

from redsun.aio import get_shared_loop

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


class LockReleasingState(LoggingPropertyMachine):
    """The engine's state, which releases every device lock on reaching idle.

    A halted plan skips its cleanup, so its ``unlock`` messages never run.
    """

    def __set__(self, obj: RunEngine, value: str) -> None:
        super().__set__(obj, value)
        if self.__get__(obj, type(obj)) == "idle":
            obj._release_locks()


class RunEngine(BlueskyRunEngine):
    """Runs plans and emits documents without blocking the calling thread.

    Wraps `bluesky.run_engine.RunEngine`: ``__call__`` runs the plan on a
    separate thread and returns a concurrent.futures.Future of its result.

    Parameters
    ----------
    md : dict[str, Any], optional
        Metadata store, a ``dict`` by default. Any object with `__getitem__`,
        `__setitem__` and `clear` works, such as historydict.HistoryDict,
        which persists history in a sqlite file.

    loop: asyncio.AbstractEventLoop, optional
        Event loop plans run on. Defaults to the shared background loop.

    preprocessors : list, optional
        Generator functions modifying a plan's messages, such as the
        ``bluesky.plans`` functions ending in 'wrapper'. ``[f, g]`` applies as
        ``f(g(plan))``.

    md_validator : Callable[dict[str, Any], None], optional
        Raises to prevent a run whose metadata it finds invalid; its return
        value is ignored.

    md_normalizer : Callable[dict[str, Any], dict[str, Any]], optional
        Like md_validator, raises for invalid metadata; otherwise returns the
        normalized metadata.

    scan_id_source : Callable[dict[str, Any], int | Awaitable[int]], optional
        Function, possibly async, returning the next scan_id. By default
        scan_id increments by 1.

    call_returns_result : bool, default True
        What the Future ``__call__`` returns holds: a ``RunEngineResult``
        describing the run if ``True``, a tuple of uids if ``False``.


    Attributes
    ----------
    md
        The metadata store described above.

    record_interruptions
        False by default. True adds an event stream recording interruptions
        (pauses, suspensions).

    state
        {'idle', 'running', 'paused'}

    suspenders
        Read-only collection of `bluesky.suspenders.SuspenderBase` objects
        that suspend and resume execution.

    preprocessors : list
        The preprocessors described above.

    msg_hook
        ``f(msg)`` called with every ``bluesky.Msg`` before it is processed,
        for logging or debugging. None by default.

    state_hook
        ``f(new_state, old_state)`` called on every state change. None by
        default.

    waiting_hook
        ``f(status_object)`` called while waiting for long-running commands
        (trigger, set, kickoff, complete), for example to show progress.

    ignore_callback_exceptions
        Boolean, False by default.

    loop : asyncio event loop
        e.g., ``asyncio.get_event_loop()`` or ``asyncio.new_event_loop()``

    max_depth
        Maximum stack depth, preventing calls to the RunEngine from inside a
        function, which breaks introspection. None by default; 2 suits the
        Python interpreter and 11 ``IPython`` (tested on 5.1.0).

    pause_msg : str
        Message printed when a run is interrupted, with instructions for
        changing the RunEngine's state. ``bluesky.run_engine.PAUSE_MSG`` by
        default.

    commands:
        The list of commands available to Msg.

    """

    sig_locks_changed = Signal(frozenset)
    """The names of the locked devices, whenever that set changes."""

    _state = LockReleasingState(RunEngineStateMachine)

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

        # register custom commands
        self._command_registry.update(
            {
                "wait_for_actions": self._wait_for_actions,
                "lock": self._lock,
                "unlock": self._unlock,
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
        plan : typing.Iterable[`bluesky.utils.Msg`]
            A generator yielding ``Msg`` objects, or an iterable returning one.
        subs : `bluesky.utils.Subscribers`, optional (positional only)
            Callbacks subscribed for this run only, given as:

            * a callable, which will be subscribed to 'all'
            * a list of callables, which again will be subscribed to 'all'
            * a dictionary, mapping specific subscriptions to callables or
              lists of callables; valid keys are {'all', 'start', 'stop',
              'event', 'descriptor'}

        Returns
        -------
        Future[RunEngineResult | tuple[str, ...]]
            Future of the plan's result, which is either:
        uids : tuple
            list of uids (i.e. RunStart Document uids) of run(s)
            if :attr:`RunEngine._call_returns_result` is ``False``
        result : :class:`RunEngineResult`
            if :attr:`RunEngine._call_returns_result` is ``True``
        """
        return self._run_in_thread(partial(super().__call__, plan, subs, **metadata_kw))

    def resume(self) -> Future[RunEngineResult | tuple[str, ...]]:
        """Resume the paused plan on a separate thread.

        Pausing completes the future ``__call__`` returned, so this returns a
        new one.

        Returns
        -------
        ``Future[RunEngineResult | tuple[str, ...]]``
            Future of the resumed plan's result.
        """
        return self._run_in_thread(super().resume)

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
        """Wait for any of the given latches to be set or reset.

        Parameters
        ----------
        msg: Msg
            Carries a map of SRLatch in `msg.args` and a timeout in
            `msg.kwargs`:

            Msg("wait_for_actions", None, latches, timeout=timeout, wait_for="set")

        Returns
        -------
        tuple[str, SRLatch] | None
            Name and latch that changed; None if the timeout expired first.
        """
        latch_map: Mapping[str, SRLatch] = msg.args[0]
        timeout: float | None = msg.kwargs.get("timeout", None)
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

        done, pending = await asyncio.wait(
            latch_tasks, return_when=asyncio.FIRST_COMPLETED, timeout=timeout
        )

        # Cancel all pending tasks
        for task in pending:
            task.cancel()

        # Return the latch that changed state
        if not done:
            return None
        completed_task = done.pop()
        task_name = completed_task.get_name()
        return task_name, latch_map[task_name]


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
