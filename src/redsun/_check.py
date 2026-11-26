"""Check a session file without building it."""

from __future__ import annotations

import logging
from itertools import chain
from typing import TYPE_CHECKING, Literal

from redsun import __version__
from redsun.errors import ConfigurationError, HookError, PluginError
from redsun.path_provider import PATH_PROVIDER_PORT, SessionPathProvider

from ._config import label
from ._hooks import distinct
from ._manifest import survey
from ._reports import FORMAT, SKIPPED, CheckReport, Component, Lookup, Problem
from .ports._wiring import class_ports
from .session._base import Session, unaccepted
from .session._declarations import Layer
from .session._layout import resolved_layout

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from ._config import SessionFile, Source
    from ._reports import Group, Status
    from .ports._wiring import PortNames

ORDER: dict[Status, int] = {"passed": 0, "undecided": 1, "failed": 2}
"""How bad each status is, so the worse of two ends decides a lookup."""


def check_report(files: Sequence[Source]) -> CheckReport:
    """Return what building *files* would find, found without building them.

    The `redsun` logger is raised above `ERROR` while the files are read, so
    the failures the report holds are not logged as well, and put back after.
    """
    logger = logging.getLogger("redsun")
    level = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        return checked(files)
    finally:
        logger.setLevel(level)


def checked(files: Sequence[Source]) -> CheckReport:
    """Read *files* as the build does, and record what it found."""
    problems = [
        Problem(kind="manifest", where=found.name, message=found.problem)
        for found in survey()
        if found.manifest is None
    ]
    where = ", ".join(label(source) for source in files)
    try:
        session = Session.from_config(list(files))
    except (ImportError, OSError, PluginError, TypeError, ValueError) as e:
        return report([*problems, Problem(kind="session", where=where, message=str(e))])
    try:
        config = session._read()
    except ConfigurationError as e:
        return report([*problems, *value_problems(e)])
    except (HookError, ImportError, TypeError, ValueError) as e:
        return report([*problems, Problem(kind="session", where=where, message=str(e))])
    return report(
        problems,
        components=list(components(session, config)),
        lookups=[
            *layout_lookups(session),
            *wiring_lookups(session, config),
            *pair_lookups(session, config),
            *stack_lookups(session),
        ],
    )


def report(
    problems: list[Problem],
    *,
    components: list[Component] | None = None,
    lookups: list[Lookup] | None = None,
) -> CheckReport:
    """Return a report of *problems* and, when reading went through, its records."""
    return CheckReport(
        redsun=__version__,
        format=FORMAT,
        problems=problems,
        components=components or [],
        lookups=lookups or [],
        skipped=list(SKIPPED),
    )


def value_problems(error: ConfigurationError) -> list[Problem]:
    """Return one `value` problem for each line *error* lists."""
    problems = []
    for line in error.problems:
        where, _, message = line.partition(": ")
        problems.append(Problem(kind="value", where=where, message=message))
    return problems


def class_path(cls: type) -> str | None:
    """Return *cls* as `module:ClassName`, or `None` for the stand-in of a class not found."""
    return None if cls is object else f"{cls.__module__}:{cls.__qualname__}"


def component(
    name: str,
    group: Group,
    cls: type | None,
    entry: object,
    status: Status,
    reason: str | None = None,
) -> Component:
    """Return the record of one component, its plugin read from its file *entry*."""
    return Component.model_validate(
        {
            "name": name,
            "group": group,
            "plugin_name": getattr(entry, "plugin_name", None),
            "plugin_id": getattr(entry, "plugin_id", None),
            "class": None if cls is None else class_path(cls),
            "status": status,
            "reason": reason,
        }
    )


def components(session: Session, config: SessionFile) -> Iterator[Component]:
    """Yield a record for each component, stack, service and hook provider."""
    stack_of = {
        half: stack.name for stack in session._stacks.values() for half in stack.roles
    }
    declarations = sorted(
        session._declarations.values(), key=lambda d: list(Layer).index(d.kind)
    )
    for declaration in declarations:
        group: Group = declaration.kind.section  # type: ignore[assignment]
        entry = getattr(config, group).get(declaration.source)
        if entry is None and declaration.name in stack_of:
            entry = config.stacks.get(stack_of[declaration.name])
        failure = session._failed.get(declaration.name)
        if failure is None and declaration.refusal is None:
            refused = unaccepted(declaration.cls, declaration.cfg_kwargs)
            if refused:
                failure = TypeError(
                    f"its class takes no {', '.join(map(repr, refused))}"
                )
        yield component(
            declaration.name,
            group,
            declaration.cls,
            entry,
            "passed" if failure is None else "failed",
            None if failure is None else str(failure),
        )
    for stack in session._stacks.values():
        yield component(
            stack.name, "stacks", stack.cls, config.stacks.get(stack.name), "passed"
        )
    for name in session._services:
        yield component(name, "services", None, config.services.get(name), "passed")
    for name, error in session._unresolved_services.items():
        yield component(
            name, "services", None, config.services.get(name), "failed", str(error)
        )
    for provider in distinct(chain.from_iterable(session.hooks.values())):
        cls = type(provider)
        yield component(cls.__name__, "hooks", cls, None, "passed")
    for hook in session._failed_hooks:
        yield component(hook.name, "hooks", None, None, "failed", str(hook.reason))


def layout_lookups(session: Session) -> Iterator[Lookup]:
    """Yield a failed lookup for each name the layout gives that no view answers to."""
    if session._window_layout is None:
        return
    placements = {
        d.name: d.placement
        for d in session._declarations.values()
        if d.kind is Layer.VIEW
    }
    _, dropped = resolved_layout(session._window_layout, placements, session.frontend)
    for name in dropped:
        yield Lookup(
            section="layout",
            name=name,
            status="failed",
            reason="no declared view or stack has this name",
        )


def component_class(session: Session, name: str) -> tuple[type | None, str | None]:
    """Return the class a wiring or pairing *name* reaches, or why it reaches none."""
    if name == PATH_PROVIDER_PORT:
        return SessionPathProvider, None
    declaration = session._declarations.get(name)
    if declaration is None or declaration.kind is Layer.DEVICE:
        return None, f"no presenter or view is declared as {name!r}"
    if name in session._failed:
        return None, f"{name!r} would not be built"
    return declaration.cls, None


def port_end(
    session: Session, path: str, kind: Literal["signal", "slot"]
) -> tuple[Status, str | None]:
    """Return whether the `component.port` *path* names a port of its class."""
    name, _, port = path.partition(".")
    if not name or not port or "." in port:
        return "failed", f"{path!r} is not a port path; expected 'component.port'"
    cls, reason = component_class(session, name)
    if cls is None:
        return "failed", reason
    names = class_ports(cls)
    found = names.signals if kind == "signal" else names.slots.keys()
    if port in found:
        return "passed", None
    listed = ", ".join(sorted(found)) or "none"
    return "undecided", f"{name!r} declares no {kind} {port!r}; its {kind}s: {listed}"


def worst(*ends: tuple[Status, str | None]) -> tuple[Status, str | None]:
    """Return the worse status of *ends*, with the reasons of the ends that are not passed."""
    status = max((status for status, _ in ends), key=ORDER.__getitem__)
    reasons = [reason for _, reason in ends if reason is not None]
    return status, "; ".join(reasons) or None


def wiring_lookups(session: Session, config: SessionFile) -> Iterator[Lookup]:
    """Yield a lookup for each link the `wiring` section names, one per target."""
    for source, targets in config.wiring.items():
        for target in [targets] if isinstance(targets, str) else targets:
            status, reason = worst(
                port_end(session, source, "signal"), port_end(session, target, "slot")
            )
            yield Lookup(
                section="wiring",
                name=f"{source} -> {target}",
                status=status,
                reason=reason,
            )


def reaches(sender: PortNames, receiver: PortNames) -> bool:
    """Return whether a signal of *sender* is named by a slot of *receiver*."""
    return any(sender.signals.intersection(names) for names in receiver.slots.values())


def paired(
    session: Session, section: Literal["pairs", "stacks"], first: str, second: str
) -> Lookup:
    """Return whether pairing *first* with *second* connects something, as their classes say."""
    name = f"{first} <-> {second}"
    (one, why_one), (other, why_other) = (
        component_class(session, first),
        component_class(session, second),
    )
    if one is None or other is None:
        reason = "; ".join(r for r in (why_one, why_other) if r is not None)
        return Lookup(section=section, name=name, status="failed", reason=reason)
    a, b = class_ports(one), class_ports(other)
    if reaches(a, b) or reaches(b, a):
        return Lookup(section=section, name=name, status="passed")
    return Lookup(
        section=section,
        name=name,
        status="undecided",
        reason="no slot of either class names a signal of the other",
    )


def pair_lookups(session: Session, config: SessionFile) -> Iterator[Lookup]:
    """Yield a lookup for each pair the `pairs` section names."""
    for first, second in config.pairs:
        yield paired(session, "pairs", first, second)


def stack_lookups(session: Session) -> Iterator[Lookup]:
    """Yield a lookup for the pairing of each stack's presenter with each of its views."""
    for stack in session._stacks.values():
        for view in stack.views.values():
            yield paired(session, "stacks", stack.presenter, view)
