"""Hook providers a session installs on its application container.

Lives at the package root because `redsun.containers` and `redsun.experimental`
both need it and neither may import the other's private modules.
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from contextlib import AbstractContextManager

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

ENTRY_KEYS = ("provider", "kwargs")

logger = logging.getLogger("redsun")


class HookError(RuntimeError):
    """A ``hooks`` configuration entry cannot be turned into a provider."""


def known_points(moments: Iterable[str]) -> str:
    """Name the hook points a container calls, to close an error message.

    A container calling none is the ordinary case for one that is not bound to
    a toolkit, so it is said in words rather than as an empty list.
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

    The only hook point that is a span rather than a moment: a splash screen
    appears before anything is built, reports progress while it is, and closes
    once the window is on screen.
    """

    @abstractmethod
    def during_build(
        self, app: AppT_contra
    ) -> AbstractContextManager[Callable[[str], None]]:
        """Return a context manager open for the whole build.

        What it yields is called with the name of each step as it starts.
        """
        ...


@dataclass(frozen=True, slots=True)
class HookSpec:
    """One provider of the configuration ``hooks`` section, and what it serves.

    *moments* holds every key the entry appeared under, so an anchor shared by
    two keys gives one spec, and one provider instance.
    """

    moments: tuple[str, ...]
    provider: str
    kwargs: Mapping[str, Any]


def parse_hook_specs(
    raw: Mapping[str, Any], moments: Mapping[str, type], owner: str
) -> list[HookSpec]:
    """Read the ``hooks`` section into one spec per distinct entry.

    Keys are the hook points *owner* calls; an entry appearing under several of
    them through a YAML anchor is one spec serving them all.

    Raises
    ------
    HookError
        If a key is not a hook point *owner* calls, an entry is not a mapping,
        carries a key other than ``provider`` and ``kwargs``, carries no string
        ``provider``, carries a non-mapping ``kwargs``, or two separate entries
        name the same provider with the same keys.
    """
    grouped: dict[int, tuple[list[str], Mapping[str, Any]]] = {}
    for moment, entry in raw.items():
        if moment not in moments:
            raise HookError(
                f"hooks key {moment!r} is not a hook point {owner} calls; "
                f"{known_points(moments)}"
            )
        if not isinstance(entry, Mapping):
            raise HookError(
                f"hooks entry {moment!r} must be a mapping, got {type(entry).__name__}"
            )
        # a YAML anchor and its alias resolve to one object, which is how a
        # session says that two hook points share a provider
        served, _ = grouped.setdefault(id(entry), ([], entry))
        served.append(moment)

    specs = [
        spec_from_entry(tuple(served), entry) for served, entry in grouped.values()
    ]
    refuse_ambiguous(specs)
    return specs


def spec_from_entry(moments: tuple[str, ...], entry: Mapping[str, Any]) -> HookSpec:
    """Read one ``hooks`` entry, named by every hook point it appeared under.

    Raises
    ------
    HookError
        If the entry carries an unknown key, no string ``provider``, or a
        ``kwargs`` that is not a mapping.
    """
    named = ", ".join(repr(moment) for moment in moments)
    unknown = sorted(key for key in entry if key not in ENTRY_KEYS)
    if unknown:
        raise HookError(
            f"hooks entry {named} carries unknown key(s) {', '.join(unknown)}; "
            "an entry takes 'provider' and 'kwargs' only, and constructor "
            "arguments go under 'kwargs'"
        )
    provider = entry.get("provider")
    if not isinstance(provider, str):
        raise HookError(
            f"hooks entry {named} must carry a string 'provider' naming a "
            f"class as 'module:ClassName', got {provider!r}"
        )
    kwargs = entry.get("kwargs", {})
    if not isinstance(kwargs, Mapping):
        raise HookError(
            f"hooks entry {named} must carry a mapping 'kwargs', "
            f"got {type(kwargs).__name__}"
        )
    return HookSpec(moments=moments, provider=provider, kwargs=kwargs)


def refuse_ambiguous(specs: Iterable[HookSpec]) -> None:
    """Refuse two separate entries naming one provider with the same keys.

    Raises
    ------
    HookError
        If two entries are indistinguishable, since whether they mean one
        shared provider or two identical ones cannot be read off the file.
    """
    seen: list[HookSpec] = []
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


def resolve_hooks(specs: Iterable[HookSpec]) -> dict[str, object]:
    """Instantiate the provider each spec names, once per spec.

    Returns one entry per hook point, so a spec serving several points maps
    them all to the same object.

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


def instantiate(spec: HookSpec) -> object:
    """Import the class *spec* names and construct it with the spec's keys.

    Raises
    ------
    HookError
        If the path is malformed, does not import, does not name a class, or
        names one that rejects the keys given.
    """
    module_name, _, class_name = spec.provider.partition(":")
    if not module_name or not class_name:
        raise HookError(
            f"hook provider {spec.provider!r} is not a class path; "
            "expected 'module:ClassName'"
        )
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
