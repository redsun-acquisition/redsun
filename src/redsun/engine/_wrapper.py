"""Wrapper for the [`bluesky.run_engine.RunEngine`]() class to allow execution without blocking the main thread."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from bluesky.run_engine import (
    RunEngine as BlueskyRunEngine,
)
from bluesky.run_engine import RunEngineResult
from bluesky.utils import RunEngineInterrupted
from event_model.documents import Document

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Awaitable, Callable
    from typing import Iterable, TypeAlias

    from bluesky.utils import Msg, Subscribers

    Preprocessor: TypeAlias = Callable[
        [Iterable[Msg], Callable[[Msg], Msg | None]], Iterable[Msg]
    ]
    MDValidator: TypeAlias = Callable[[dict[str, Any]], None]
    MDNormalizer: TypeAlias = Callable[[dict[str, Any]], dict[str, Any]]
    MDScanIDSource: TypeAlias = Callable[[dict[str, Any]], int | Awaitable[int]]


def default_scan_id_source(md: dict[str, Any]) -> int:
    scan_id: int = md.get("scan_id", 0)
    return scan_id + 1


__all__ = ["RunEngine", "RunEngineResult", "RunEngineInterrupted", "Document"]

REResultType = RunEngineResult | tuple[str, ...]


class RunEngine(BlueskyRunEngine):
    """The Run Engine execute messages and emits Documents.

    This is a wrapper for the `bluesky.run_engine.RunEngine` class that
    allows execution without blocking the main thread.
    The main difference is that the ``__call__`` method
    is executed in a separate thread,
    and it returns a concurrent.futures.Future object
    representing the result of the plan execution.

    Parameters
    ----------
    md : dict[str, Any], optional
        The default is a standard Python dictionary, but fancier
        objects can be used to store long-term history and persist
        it between sessions. The standard configuration
        instantiates a Run Engine with historydict.HistoryDict, a
        simple interface to a sqlite file. Any object supporting
        `__getitem__`, `__setitem__`, and `clear` will work.

    loop: asyncio.AbstractEventLoop, optional
        An asyncio event loop to be used for executing plans. If not provided,
        the RunEngine will create a new event loop using ``asyncio.new_event_loop()``;
        e.g., ``asyncio.get_event_loop()`` or ``asyncio.new_event_loop()``

    preprocessors : list, optional
        Generator functions that take in a plan (generator instance) and
        modify its messages on the way out. Suitable examples include
        the functions in the module ``bluesky.plans`` with names ending in
        'wrapper'.  Functions are composed in order: the preprocessors
        ``[f, g]`` are applied like ``f(g(plan))``.

    md_validator : Callable[dict[str, Any], None], optional
        a function that raises and prevents starting a run if it deems
        the metadata to be invalid or incomplete
        Function should raise if md is invalid. What that means is
        completely up to the user. The function's return value is
        ignored.

    md_normalizer : Callable[dict[str, Any], dict[str, Any]], optional
        a function that, similar to md_validator, raises and prevents starting
        a run if it deems the metadata to be invalid or incomplete.
        If it succeeds, it returns the normalized/transformed version of
        the original metadata.
        Function should raise if md is invalid. What that means is
        completely up to the user.
        Expected return: normalized metadata

    scan_id_source : Callable[dict[str, Any], int | Awaitable[int]], optional
        a (possibly async) function that will be used to calculate scan_id.
        Default is to increment scan_id by 1 each time. However you could pass
        in a customized function to get a scan_id from any source.
        Expected return: updated scan_id value

    call_returns_result : bool, default True
        A flag that controls the return value of ``__call__``.
        If ``True``, the ``RunEngine`` will return a :class:``RunEngineResult``
        object that contains information about the plan that was run.
        If ``False``, the ``RunEngine`` will return a tuple of uids.
        The potential return value is encapsulated in the returned Future object,
        accessible via ``future.result()``.
        Defaults to ``True``.


    Attributes
    ----------
    md
        Direct access to the dict-like persistent storage described above

    record_interruptions
        False by default. Set to True to generate an extra event stream
        that records any interruptions (pauses, suspensions).

    state
        {'idle', 'running', 'paused'}

    suspenders
        Read-only collection of `bluesky.suspenders.SuspenderBase` objects
        which can suspend and resume execution; see related methods.

    preprocessors : list
        Generator functions that take in a plan (generator instance) and
        modify its messages on the way out. Suitable examples include
        the functions in the module ``bluesky.plans`` with names ending in
        'wrapper'.  Functions are composed in order: the preprocessors
        ``[f, g]`` are applied like ``f(g(plan))``.

    msg_hook
        Callable that receives all messages before they are processed
        (useful for logging or other development purposes); expected
        signature is ``f(msg)`` where ``msg`` is a ``bluesky.Msg``, a
        kind of namedtuple; default is None.

    state_hook
        Callable with signature ``f(new_state, old_state)`` that will be
        called whenever the RunEngine's state attribute is updated; default
        is None

    waiting_hook
        Callable with signature ``f(status_object)`` that will be called
        whenever the RunEngine is waiting for long-running commands
        (trigger, set, kickoff, complete) to complete. This hook is useful to
        incorporate a progress bar.

    ignore_callback_exceptions
        Boolean, False by default.

    call_returns_result
        Boolean, False by default. If False, RunEngine will return uuid list
        after running a plan. If True, RunEngine will return a RunEngineResult
        object that contains the plan result, error status, and uuid list.

    loop : asyncio event loop
        e.g., ``asyncio.get_event_loop()`` or ``asyncio.new_event_loop()``

    max_depth
        Maximum stack depth; set this to prevent users from calling the
        RunEngine inside a function (which can result in unexpected
        behavior and breaks introspection tools). Default is None.
        For built-in Python interpreter, set to 2. For IPython, set to 11
        (tested on IPython 5.1.0; other versions may vary).

    pause_msg : str
        The message printed when a run is interrupted. This message
        includes instructions of changing the state of the RunEngine.
        It is set to ``bluesky.run_engine.PAUSE_MSG`` by default and
        can be modified based on needs.

    commands:
        The list of commands available to Msg.

    """

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
        # force the context_managers to be empty,
        # otherwise the RunEngine will try to use the
        # SignalHandler context manager
        self._executor = ThreadPoolExecutor(max_workers=1)

        super().__init__(
            md=md,
            loop=loop,
            preprocessors=preprocessors,
            md_validator=md_validator,
            md_normalizer=md_normalizer,
            scan_id_source=scan_id_source,  # type: ignore[arg-type]
            call_returns_result=call_returns_result,
            context_managers=[],
        )

        # override pause message to be an empty string
        self.pause_msg = ""

    def __call__(  # type: ignore[override]
        self,
        plan: Iterable[Msg],
        subs: Subscribers | None = None,
        /,
        **metadata_kw: Any,
    ) -> Future[RunEngineResult | tuple[str, ...]]:
        """Execute a plan.

        Any keyword arguments will be interpreted as metadata and recorded with
        any run(s) created by executing the plan. Notice that the plan
        (required) and extra subscriptions (optional) must be given as
        positional arguments.

        Parameters
        ----------
        plan : typing.Iterable[`bluesky.utils.Msg`]
            A generator or that yields ``Msg`` objects (or an iterable that
            returns such a generator).
        subs : `bluesky.utils.Subscribers`, optional (positional only)
            Temporary subscriptions (a.k.a. callbacks) to be used on this run.
            For convenience, any of the following are accepted:

            * a callable, which will be subscribed to 'all'
            * a list of callables, which again will be subscribed to 'all'
            * a dictionary, mapping specific subscriptions to callables or
              lists of callables; valid keys are {'all', 'start', 'stop',
              'event', 'descriptor'}

        Returns
        -------
        Future[RunEngineResult | tuple[str, ...]]
            Future object representing the result of the plan execution.

        The result contained in the future is either:
        uids : tuple
            list of uids (i.e. RunStart Document uids) of run(s)
            if :attr:`RunEngine._call_returns_result` is ``False``
        result : :class:`RunEngineResult`
            if :attr:`RunEngine._call_returns_result` is ``True``
        """
        return self._executor.submit(
            super().__call__,
            plan,
            subs,
            **metadata_kw,
        )

    def resume(self) -> Future[RunEngineResult | tuple[str, ...]]:
        """Resume the paused plan in a separate thread.

        If the plan has been paused, the initial
        future returned by ``__call__`` will be set as completed.

        With this method, the plan is resumed in a separate thread,
        and a new future is returned.

        Returns
        -------
        ``Future[RunEngineResult | tuple[str, ...]]``
            Future object representing the result of the resumed plan.
        """
        return self._executor.submit(super().resume)
