"""Hook providers a session installs on its application container."""

from __future__ import annotations

import logging
import re
from abc import abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Protocol, TypeVar, runtime_checkable

from pydantic import AfterValidator, BaseModel

from redsun.errors import HookError

from ._manifest import class_path, import_class

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from contextlib import AbstractContextManager

__all__ = [
    "ConfiguresApplication",
    "ConfiguresMainView",
    "ConfirmsClose",
    "CreatesApplication",
    "Many",
    "WrapsBuild",
]

AppT_co = TypeVar("AppT_co", covariant=True)
AppT_contra = TypeVar("AppT_contra", contravariant=True)
ViewT_contra = TypeVar("ViewT_contra", contravariant=True)

logger = logging.getLogger("redsun")


@dataclass(frozen=True)
class Many:
    """Marks a hook point that takes any number of providers, run in order.

    A session class writes it in `hook_points` around the point's protocol.
    A point given its protocol alone takes exactly one provider.
    """

    protocol: type
    """The protocol every provider at the point satisfies."""


@dataclass(frozen=True)
class HookFailure:
    """Why a hook provider was skipped, and the points it was to serve."""

    points: tuple[str, ...]
    """The hook points the provider was installed at, or declared for."""

    reason: BaseException
    """What it raised."""


def point_protocol(point: type | Many) -> type:
    """Return the protocol a provider at *point* satisfies."""
    return point.protocol if isinstance(point, Many) else point


def takes_many(point: type | Many) -> bool:
    """Return whether *point* takes any number of providers."""
    return isinstance(point, Many)


def known_points(moments: Iterable[str]) -> str:
    """Name the hook points a container calls, to end an error message.

    A container bound to no toolkit calls none, which is said in words, not as
    an empty list.
    """
    listed = ", ".join(moments)
    if not listed:
        return (
            "it calls none. Every hook point belongs to a toolkit, so a hook "
            "is declared on a toolkit session such as QtSession"
        )
    return f"expected one of: {listed}"


@runtime_checkable
class CreatesApplication(Protocol[AppT_co]):
    """Supplies the toolkit's application object instead of the container.

    The point takes one provider. If it cannot be built, the build stops: a
    session told which application to run on does not start on another.
    """

    @abstractmethod
    def create_application(self, argv: list[str]) -> AppT_co:
        """Return the application object the session runs on."""
        ...


@runtime_checkable
class ConfiguresApplication(Protocol[AppT_contra]):
    """Adjusts the application before any view is constructed.

    The point takes any number of providers, called in order. One that
    raises is logged and skipped. What a provider changes on the application
    it puts back in a `shutdown` method.
    """

    @abstractmethod
    def configure_application(self, app: AppT_contra) -> None:
        """Act on *app*, which every view is about to be built against."""
        ...


@runtime_checkable
class ConfiguresMainView(Protocol[ViewT_contra]):
    """Adjusts the main window after it is built and before it is shown.

    The point takes any number of providers, called in order. One that
    raises is logged and skipped. What a provider changes outside the window
    it puts back in a `shutdown` method.
    """

    @abstractmethod
    def configure_main_view(self, view: ViewT_contra) -> None:
        """Act on *view*, the window the session is about to show."""
        ...


@runtime_checkable
class ConfirmsClose(Protocol):
    """Decides whether the session may close, and can refuse.

    The session acts on this point's answer, where it only tells the other
    points what happened. `False` leaves the session running. The point takes
    one provider. If it raises, it is logged and skipped, and the session
    decides by its own rule.
    """

    @abstractmethod
    def confirm_close(self) -> bool:
        """Return whether the session may close now."""
        ...


@runtime_checkable
class WrapsBuild(Protocol[AppT_contra]):
    """Surrounds the build, from before the first component to after the window.

    The one hook point that is a span, not a moment: a splash screen appears
    before anything is built, reports progress, and closes once the window is
    on screen. The point takes any number of providers: their spans are
    opened in order and left in reverse. One that raises, opening its span or
    being told a step, is logged and told nothing more, and a span it opened
    is still left.
    """

    @abstractmethod
    def during_build(
        self, app: AppT_contra
    ) -> AbstractContextManager[Callable[[str], None]]:
        """Return a context manager open for the whole build.

        What it yields is called with the name of each step as it starts.
        """
        ...


def refuse_unknown_points(
    specs: Iterable[HookGroup], moments: Mapping[str, type | Many], owner: str
) -> None:
    """Refuse an entry of the `hooks` section under a key *owner* does not call.

    Raises
    ------
    HookError
        If a key is not a hook point *owner* calls.
    """
    for spec in specs:
        for moment in spec.moments:
            if moment not in moments:
                raise HookError(
                    f"hooks key {moment!r} is not a hook point {owner} calls; "
                    f"{known_points(moments)}"
                )


def refuse_ambiguous(
    specs: Iterable[HookGroup], same: Callable[[str], str] = str
) -> None:
    """Refuse two separate entries naming one provider with the same keys.

    *same* turns a provider's name into what it stands for, so a short name
    and the class path behind it count as one provider.

    Raises
    ------
    HookError
        If two entries are identical, since the file cannot say whether they
        mean one shared provider or two.
    """
    seen: list[HookGroup] = []
    for spec in specs:
        for other in seen:
            if (
                same(spec.provider) == same(other.provider)
                and spec.kwargs == other.kwargs
            ):
                first = ", ".join(repr(moment) for moment in other.moments)
                second = ", ".join(repr(moment) for moment in spec.moments)
                share = (
                    "Anchor the entry and alias it"
                    if ":" in spec.provider
                    else "Write it once as a mapping, anchored, and alias it "
                    f"(&name {{provider: {spec.provider}}}, then *name)"
                )
                raise HookError(
                    f"hook provider {spec.provider!r} is named twice, at "
                    f"{first} and at {second}, with the same keys. {share} to "
                    "share one provider, or give the two different keys to "
                    "build two."
                )
        seen.append(spec)


def entries_by_point(groups: Sequence[HookGroup]) -> dict[str, list[HookGroup]]:
    """Return the entries of each hook point, in the order the file lists them."""
    placed = sorted(
        (moment, position, index)
        for index, group in enumerate(groups)
        for moment, position in zip(group.moments, group.positions, strict=True)
    )
    by_point: dict[str, list[HookGroup]] = {}
    for moment, _, index in placed:
        by_point.setdefault(moment, []).append(groups[index])
    return by_point


def refuse_crowded(
    sources: Mapping[str, Sequence[object]],
    points: Mapping[str, type | Many],
    owner: str,
) -> None:
    """Refuse more than one provider at a hook point that takes one.

    Raises
    ------
    HookError
        If *owner* and its configuration name several between them.
    """
    for moment, named in sources.items():
        if len(named) > 1 and not takes_many(points[moment]):
            raise HookError(
                f"hook point {moment!r} takes one provider, and {owner} and "
                f"its configuration name {len(named)} between them; drop all "
                "but one"
            )


def refuse_misfits(
    resolved: Mapping[str, Sequence[object]], points: Mapping[str, type | Many]
) -> None:
    """Refuse a provider lacking the method of a hook point it is installed at.

    Raises
    ------
    HookError
        If a provider does not implement its point's protocol.
    """
    for moment, providers in resolved.items():
        protocol = point_protocol(points[moment])
        for provider in providers:
            if not isinstance(provider, protocol):
                raise HookError(
                    f"hook provider {type(provider).__name__!r} at {moment!r} "
                    f"does not implement {protocol.__name__}"
                )


def provider_from_file(spec: HookGroup, path: str) -> object:
    """Import the class at *path*, which *spec* names, and construct it with the spec's keys.

    Raises
    ------
    HookError
        If the path does not import, does not name a class, or names one that
        rejects the keys given.
    """
    try:
        imported = import_class(path)
    except (ImportError, TypeError) as e:
        raise HookError(f"cannot import hook provider {spec.provider!r}: {e}") from e
    try:
        return imported(**spec.kwargs)
    except Exception as e:
        raise HookError(
            f"cannot construct hook provider {spec.provider!r} with "
            f"{sorted(spec.kwargs)}: {e}"
        ) from e


def distinct(objects: Iterable[object]) -> tuple[object, ...]:
    """Return *objects* without repeats, by identity, in first-seen order."""
    seen: dict[int, object] = {}
    for obj in objects:
        seen.setdefault(id(obj), obj)
    return tuple(seen.values())


def provider_name(value: str) -> str:
    """Refuse text that is neither a class path nor a short name such as `napari`."""
    if ":" in value:
        return class_path(value)
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", value):
        raise ValueError(
            f"{value!r} is neither a class path ('module:ClassName') nor the "
            "short name of a built-in provider"
        )
    return value


ProviderName = Annotated[str, AfterValidator(provider_name)]
"""A hook provider named by its class path or by a built-in provider's short name."""


class HookGroup(BaseModel, extra="forbid", frozen=True, use_attribute_docstrings=True):
    """One provider of the `hooks` section, and every hook point it serves."""

    moments: tuple[str, ...]
    """The hook points the entry appeared under."""

    positions: tuple[int, ...]
    """Where the entry stands in the list of each hook point in `moments`."""

    provider: ProviderName
    """The provider's class, as `module:ClassName`, or a built-in provider's short name."""

    kwargs: dict[str, Any] = {}
    """Keywords the provider is constructed with."""


def group_hook_entries(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return one entry per distinct object in *raw*, with the hook points naming it.

    A hook point holds one entry or a list of them. An entry written as a
    provider's name alone serves its own hook point only: unlike a mapping, a
    name cannot be anchored and aliased to share one provider.

    Raises
    ------
    ValueError
        If an entry is neither a mapping nor a name.
    """
    groups: dict[object, dict[str, Any]] = {}
    for moment, value in raw.items():
        for position, entry in enumerate(value if isinstance(value, list) else [value]):
            check_hook_entry(moment, entry)
            # a YAML anchor and its alias resolve to one object; once validated
            # they would be two equal copies, so sharing is read here or never.
            # A name is its own group each time it is written.
            shared = isinstance(entry, Mapping)
            key: object = id(entry) if shared else (moment, position)
            fields = entry if shared else {"provider": entry}
            group = groups.setdefault(key, {**fields, "moments": (), "positions": ()})
            group["moments"] += (moment,)
            group["positions"] += (position,)
    return list(groups.values())


def check_hook_entry(moment: str, entry: object) -> None:
    """Refuse an entry of the `hooks` section that is not a mapping or a name.

    Raises
    ------
    ValueError
        If *entry* is anything else, or a mapping holding a key the model
        fills in itself.
    """
    if isinstance(entry, str):
        return
    if not isinstance(entry, Mapping):
        # pydantic turns a ValueError raised in a validator into a
        # ValidationError at the entry's location; a TypeError escapes
        raise ValueError(  # noqa: TRY004
            f"hooks entry {moment!r} must be a mapping, a provider's name or a "
            f"list of them, got {type(entry).__name__}"
        )
    for reserved in ("moments", "positions"):
        if reserved in entry:
            raise ValueError(
                f"hooks entry {moment!r} carries unknown key {reserved!r}; an "
                "entry takes 'provider' and 'kwargs' only"
            )
