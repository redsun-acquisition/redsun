"""Hook providers a session installs on its application container."""

from __future__ import annotations

import logging
from abc import abstractmethod
from collections.abc import Mapping
from importlib import import_module
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, TypeAdapter, ValidationError

from ._manifest import ClassPath

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from contextlib import AbstractContextManager

    from redsun.containers.components import _HookField as HookField

__all__ = [
    "ConfiguresApplication",
    "ConfiguresMainView",
    "CreatesApplication",
    "HookError",
    "WrapsBuild",
]

AppT_co = TypeVar("AppT_co", covariant=True)
AppT_contra = TypeVar("AppT_contra", contravariant=True)
ViewT_contra = TypeVar("ViewT_contra", contravariant=True)

logger = logging.getLogger("redsun")


class HookError(RuntimeError):
    """A ``hooks`` configuration entry cannot be turned into a provider."""


def known_points(moments: Iterable[str]) -> str:
    """Name the hook points a container calls, to end an error message.

    A container bound to no toolkit calls none, which is said in words, not as
    an empty list.
    """
    listed = ", ".join(moments)
    if not listed:
        return (
            "it calls none. Every hook point belongs to a toolkit, so a hook "
            "is declared on a toolkit container such as QtAppContainer"
        )
    return f"expected one of: {listed}"


@runtime_checkable
class CreatesApplication(Protocol[AppT_co]):
    """Supplies the toolkit's application object instead of the container."""

    @abstractmethod
    def create_application(self, argv: list[str]) -> AppT_co:
        """Return the application object the session runs on."""
        ...


@runtime_checkable
class ConfiguresApplication(Protocol[AppT_contra]):
    """Adjusts the application before any view is constructed."""

    @abstractmethod
    def configure_application(self, app: AppT_contra) -> None:
        """Act on *app*, which every view is about to be built against."""
        ...


@runtime_checkable
class ConfiguresMainView(Protocol[ViewT_contra]):
    """Adjusts the main window after it is built and before it is shown."""

    @abstractmethod
    def configure_main_view(self, view: ViewT_contra) -> None:
        """Act on *view*, the window the session is about to show."""
        ...


@runtime_checkable
class WrapsBuild(Protocol[AppT_contra]):
    """Surrounds the build, from before the first component to after the window.

    The one hook point that is a span, not a moment: a splash screen appears
    before anything is built, reports progress, and closes once the window is
    on screen.
    """

    @abstractmethod
    def during_build(
        self, app: AppT_contra
    ) -> AbstractContextManager[Callable[[str], None]]:
        """Return a context manager open for the whole build.

        What it yields is called with the name of each step as it starts.
        """
        ...


def parse_hook_specs(
    raw: Mapping[str, Any], moments: Mapping[str, type], owner: str
) -> list[HookGroup]:
    """Read the ``hooks`` section into one group per distinct entry.

    Keys are the hook points *owner* calls; an entry under several keys through
    a YAML anchor is one group serving all of them.

    Raises
    ------
    HookError
        If a key is not a hook point *owner* calls, an entry is not a mapping
        of a class path ``provider`` and a mapping ``kwargs``, or two separate
        entries name the same provider with the same keys.
    """
    for moment in raw:
        if moment not in moments:
            raise HookError(
                f"hooks key {moment!r} is not a hook point {owner} calls; "
                f"{known_points(moments)}"
            )
    try:
        entries = group_hook_entries(raw)
    except ValueError as e:
        raise HookError(str(e)) from None
    try:
        groups = HOOK_GROUPS.validate_python(entries)
    except ValidationError as e:
        raise HookError(hook_problems(entries, e)) from None
    refuse_ambiguous(groups)
    return groups


def hook_problems(entries: list[dict[str, Any]], error: ValidationError) -> str:
    """Say what is wrong with each grouped entry, naming its hook points."""
    lines = []
    for problem in error.errors():
        index, *rest = problem["loc"]
        named = ", ".join(repr(moment) for moment in entries[int(index)]["moments"])
        key = ".".join(str(part) for part in rest)
        if problem["type"] == "extra_forbidden":
            lines.append(
                f"hooks entry {named} carries unknown key {key!r}; an entry takes "
                "'provider' and 'kwargs' only, and constructor arguments go "
                "under 'kwargs'"
            )
        else:
            lines.append(f"hooks entry {named}: {key}: {problem['msg']}")
    return "\n".join(lines)


def refuse_ambiguous(specs: Iterable[HookGroup]) -> None:
    """Refuse two separate entries naming one provider with the same keys.

    Raises
    ------
    HookError
        If two entries are identical, since the file cannot say whether they
        mean one shared provider or two.
    """
    seen: list[HookGroup] = []
    for spec in specs:
        for other in seen:
            if spec.provider == other.provider and dict(spec.kwargs) == dict(
                other.kwargs
            ):
                first = ", ".join(repr(moment) for moment in other.moments)
                second = ", ".join(repr(moment) for moment in spec.moments)
                raise HookError(
                    f"hook provider {spec.provider!r} is named twice, at "
                    f"{first} and at {second}, with the same keys. Anchor the "
                    "entry and alias it to share one provider, or give the two "
                    "different keys to build two."
                )
        seen.append(spec)


def resolve_hooks(specs: Iterable[HookGroup]) -> dict[str, object]:
    """Instantiate the provider each spec names, once per spec.

    Returns one entry per hook point; a spec serving several points maps them
    to one object.

    Raises
    ------
    HookError
        If a provider path is malformed, names a module or attribute that does
        not exist, or names something that cannot be instantiated with the
        keys given.
    """
    resolved: dict[str, object] = {}
    for spec in specs:
        provider = instantiate(spec)
        for moment in spec.moments:
            resolved[moment] = provider
    return resolved


def instantiate(spec: HookGroup) -> object:
    """Import the class *spec* names and construct it with the spec's keys.

    Raises
    ------
    HookError
        If the path does not import, does not name a class, or names one that
        rejects the keys given.
    """
    module_name, _, class_name = spec.provider.partition(":")
    try:
        imported = getattr(import_module(module_name), class_name)
    except (ImportError, AttributeError) as e:
        raise HookError(f"cannot import hook provider {spec.provider!r}: {e}") from e
    if not isinstance(imported, type):
        raise HookError(
            f"hook provider {spec.provider!r} names {imported!r}, which is not a class"
        )
    try:
        return imported(**spec.kwargs)
    except TypeError as e:
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


def build_hook_provider(
    owner: str, hook_keys: Mapping[str, type], moment: str, field: HookField
) -> object:
    """Construct the provider the container *owner* declares at *moment*.

    Raises
    ------
    HookError
        If *moment* is not among *hook_keys*, the provider
        rejects the keys given, or it does not implement the point's
        protocol.
    """
    if moment not in hook_keys:
        raise HookError(
            f"{owner} declares a hook at {moment!r}, which is not a "
            f"hook point it calls; {known_points(hook_keys)}"
        )
    declared = field.provider
    if isinstance(declared, type):
        try:
            provider: object = declared(**field.kwargs)
        except TypeError as e:
            raise HookError(
                f"cannot construct hook provider {declared.__name__!r} "
                f"declared at {moment!r} with {sorted(field.kwargs)}: {e}"
            ) from e
    else:
        provider = declared
    protocol = hook_keys[moment]
    if not isinstance(provider, protocol):
        raise HookError(
            f"hook provider {type(provider).__name__!r} declared at "
            f"{moment!r} does not implement {protocol.__name__}"
        )
    return provider


class HookGroup(BaseModel, extra="forbid", frozen=True, use_attribute_docstrings=True):
    """One provider of the ``hooks`` section, and every hook point it serves."""

    moments: tuple[str, ...]
    """The hook points the entry appeared under."""

    provider: ClassPath
    """The provider's class, as ``module:ClassName``."""

    kwargs: dict[str, Any] = {}
    """Keywords the provider is constructed with."""


def group_hook_entries(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return one entry per distinct object in *raw*, with the hook points naming it.

    Raises
    ------
    ValueError
        If an entry is not a mapping.
    """
    grouped: dict[int, tuple[list[str], Mapping[str, Any]]] = {}
    for moment, entry in raw.items():
        if not isinstance(entry, Mapping):
            # pydantic turns a ValueError raised in a validator into a
            # ValidationError at the entry's location; a TypeError escapes
            raise ValueError(  # noqa: TRY004
                f"hooks entry {moment!r} must be a mapping, got {type(entry).__name__}"
            )
        # a YAML anchor and its alias resolve to one object; once validated
        # they would be two equal copies, so sharing is read here or never
        if "moments" in entry:
            raise ValueError(
                f"hooks entry {moment!r} carries unknown key 'moments'; an entry "
                "takes 'provider' and 'kwargs' only"
            )
        served, _ = grouped.setdefault(id(entry), ([], entry))
        served.append(moment)
    return [{**entry, "moments": tuple(served)} for served, entry in grouped.values()]


HOOK_GROUPS = TypeAdapter(list[HookGroup])
"""Validates the grouped entries of a ``hooks`` section."""
