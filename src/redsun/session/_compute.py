"""The pools a session makes and the executors it hands its components."""

from __future__ import annotations

import logging
from functools import partial
from typing import TYPE_CHECKING, Any, TypeVar, cast, get_origin

from redsun.compute import Limits

from .._structural import without_none
from ..compute._future import BrokenPool
from ..compute._pool import Pool, PoolExecutor, pool_key
from ..compute._processes import ProcessExecutor, ProcessPool
from ..compute._settings import (
    ProcessPoolSettings,
    compute_cores,
    physical_cores,
    split,
)
from ..compute._threads import ThreadPool
from ..compute._usage import Watchdog
from ..injection._registry import SESSION
from ._factories import resolved
from ._protocols import HasSetup

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Generator, Mapping

    from redsun.compute import ThreadPoolSettings
    from redsun.injection import Registry

    from .._config import ComputeConfig
    from ..compute._future import Delivery

E = TypeVar("E", bound=PoolExecutor[Any])

logger = logging.getLogger("redsun")


def classes_of(fn: Callable[..., Any]) -> dict[str, type]:
    """Return the parameters of *fn* annotated with a class, `| None` removed."""
    found: dict[str, type] = {}
    signature = resolved(fn, getattr(fn, "__qualname__", repr(fn)))
    for pname, param in signature.parameters.items():
        hint = without_none(param.annotation)
        if isinstance(hint, type) and get_origin(hint) is None:
            found[pname] = hint
    return found


def executor_params(fn: Callable[..., Any]) -> dict[str, type[PoolExecutor[Any]]]:
    """Return the parameters of *fn* asking for an executor, by executor class."""
    return {
        pname: kind
        for pname, kind in classes_of(fn).items()
        if issubclass(kind, PoolExecutor)
    }


def component_kinds(cls: type) -> set[type[PoolExecutor[Any]]]:
    """Return the executor classes the constructor and the `setup` of *cls* ask for."""
    kinds = set(executor_params(cls).values())
    if issubclass(cls, HasSetup):
        kinds.update(executor_params(cls.setup).values())
    return kinds


def asks_for_pool(owner: str, fn: Callable[..., Any]) -> TypeError | None:
    """Return why *owner* cannot be given what *fn* asks for, when it asks for a pool."""
    found = next(
        (
            (pname, kind)
            for pname, kind in classes_of(fn).items()
            if issubclass(kind, Pool)
        ),
        None,
    )
    if found is None:
        return None
    pname, kind = found
    executor = next(
        (e for e in PoolExecutor.__subclasses__() if e.pool_type is kind),
        PoolExecutor,
    )
    return TypeError(
        f"{owner} asks for {kind.__name__} in '{pname}'; "
        f"ask for {executor.__name__} instead"
    )


def pool_resource(
    pool_type: type[Pool],
    settings: ThreadPoolSettings | ProcessPoolSettings,
    limits: Limits,
    delivery: Delivery,
    owner: str | None = None,
) -> Callable[[], Generator[Pool, None, None]]:
    """Return the provider of a pool of *pool_type*, made from *settings* on its first request.

    A process pool is made for *owner*, which its workers' log records are
    filed under.
    """

    # a generator function of its own: `diwire` reads a provider's source to
    # check its yield sits in a try/finally, which a partial does not have
    def provide() -> Generator[Pool, None, None]:
        extra = () if owner is None else (owner,)
        resource = pool_type.resource(settings, limits, delivery, *extra)
        try:
            yield next(resource)
        finally:
            resource.close()

    return provide


class SessionCompute:
    """The pools of one session, their settings, and the executors it handed out."""

    __slots__ = (
        "broken",
        "config",
        "cores",
        "delivery",
        "executors",
        "limits",
        "registry",
        "settings",
        "watchdog",
    )

    def __init__(
        self, config: ComputeConfig, delivery: Delivery, registry: Registry
    ) -> None:
        self.cores = 0
        self.config = config
        self.registry = registry
        self.limits = Limits(config.switch_interval_ms)
        self.delivery = delivery
        self.settings: dict[
            tuple[type[Pool], str | None], ThreadPoolSettings | ProcessPoolSettings
        ] = {}
        self.executors: dict[
            tuple[str, type[PoolExecutor[Any]]], PoolExecutor[Any]
        ] = {}
        self.broken: list[tuple[str, str]] = []
        self.watchdog = Watchdog()

    def register(
        self,
        owners: Mapping[str, set[type[PoolExecutor[Any]]]],
        workers: Mapping[str, int],
    ) -> None:
        """Register the pools the executors *owners* ask for submit to, made on their first request.

        A pool other than the process pool is shared. Each owner asking for a
        `ProcessExecutor` has a process pool of its own, of `workers[owner]`
        processes, else `compute.processes`, else its share of the compute
        cores.
        """
        kinds = set().union(*owners.values())
        if not kinds:
            return
        self.cores = compute_cores(
            physical_cores(), cap=self.config.cores, reserve=self.config.reserve
        )
        for kind in kinds:
            pool_type = kind.pool_type
            if pool_type is ProcessPool or (pool_type, None) in self.settings:
                continue
            settings = split(self.config.preset, self.cores)
            self.settings[pool_type, None] = settings
            self.registry.register_resource(
                pool_key(pool_type, None),
                pool_resource(pool_type, settings, self.limits, self.delivery),
                owner=SESSION,
                internal=True,
            )
        asking = [name for name, held in owners.items() if ProcessExecutor in held]
        for name in workers.keys() - set(asking):
            logger.warning(
                f"{name} gives 'workers' but asks for no ProcessExecutor; ignored"
            )
        share = max(1, self.cores // max(len(asking), 1))
        for name in asking:
            count = workers.get(name, self.config.processes or share)
            process_settings = ProcessPoolSettings(count, priority=self.config.priority)
            self.settings[ProcessPool, name] = process_settings
            self.registry.register_resource(
                pool_key(ProcessPool, name),
                pool_resource(
                    ProcessPool, process_settings, self.limits, self.delivery, name
                ),
                owner=SESSION,
                internal=True,
            )
        total = sum(
            s.processes
            for s in self.settings.values()
            if isinstance(s, ProcessPoolSettings)
        )
        if total > self.cores:
            logger.warning(
                f"Process pools have {total} workers in all,"
                f" more than the {self.cores} compute cores"
            )

    def executor(
        self,
        cls: type[E],
        owner: str,
        on_release: Callable[[Callable[[], None]], None],
    ) -> E:
        """Return the executor of *cls* for *owner*, making it and its pool on the first request."""
        held = self.executors.get((owner, cls))
        if held is None:
            group = owner if issubclass(cls, ProcessExecutor) else None
            provide = next(self.registry.providers(pool_key(cls.pool_type, group)))
            pool = cast("Pool", provide())
            held = cls(pool, owner)
            self.executors[owner, cls] = held
            on_release(partial(held.shutdown, wait=False, cancel_futures=True))
        return cast("E", held)

    def start(self, built: Collection[str]) -> None:
        """Start each pool a component in *built* holds, after limiting native threads.

        The limits stay until `limits.restore` runs. A pool that cannot start
        is logged and recorded in `broken`.
        """
        pools = list(
            dict.fromkeys(
                held._pool
                for (owner, _), held in self.executors.items()
                if owner in built
            )
        )
        if not pools:
            return
        # every thread pool is split from the same cores, so any of them gives
        # the native threads; process workers apply their own limits
        threaded = next((p for p in pools if isinstance(p, ThreadPool)), None)
        if threaded is not None:
            self.limits.apply(threaded.native_threads)
            self.watchdog.start()
        for pool in pools:
            try:
                pool.start()
            except BrokenPool as error:
                label = type(pool).__name__
                self.broken.append((label, str(error)))
                logger.error(f"{label} is broken: {error}")

    def summary(self) -> list[str]:
        """Return the lines the build summary adds, none when no pool was asked for."""
        if not self.settings:
            return []
        lines = [f"Compute: {self.cores} cores, preset {self.config.preset}"]
        for (kind, owner), s in self.settings.items():
            if isinstance(s, ProcessPoolSettings):
                lines.append(
                    f"{kind.__name__} of {owner}: {s.processes} processes,"
                    f" priority {s.priority}"
                )
            else:
                lines.append(
                    f"{kind.__name__}: {s.threads} threads, {s.native_threads} native threads each"
                )
        if self.broken:
            lines.append(
                "Broken pools: "
                + ", ".join(f"{label} ({reason})" for label, reason in self.broken)
            )
        return lines
