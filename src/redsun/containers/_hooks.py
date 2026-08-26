"""Hook providers a session installs on its application container."""

from __future__ import annotations

import logging
from abc import abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from redsun.containers.container import AppContainer

__all__ = ["ConfiguresBuild", "HookError"]

logger = logging.getLogger("redsun")


class HookError(RuntimeError):
    """A ``hooks`` configuration entry cannot be turned into a provider."""


@runtime_checkable
class ConfiguresBuild(Protocol):
    """Adjusts the build sequence before any phase of it runs."""

    @abstractmethod
    def configure_build(self, container: AppContainer) -> None:
        """Register or remove build phases on *container*."""
        ...


@dataclass(frozen=True, slots=True)
class HookSpec:
    """One entry of the configuration ``hooks`` section."""

    provider: str
    kwargs: Mapping[str, Any]


def parse_hook_specs(raw: Sequence[Mapping[str, Any]]) -> list[HookSpec]:
    """Read the ``hooks`` section into one spec per entry.

    Raises
    ------
    HookError
        If an entry is not a mapping, or carries no string ``provider`` key.
    """
    specs: list[HookSpec] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            raise HookError(
                f"hooks entry {index} must be a mapping, got {type(entry).__name__}"
            )
        provider = entry.get("provider")
        if not isinstance(provider, str):
            raise HookError(
                f"hooks entry {index} must carry a string 'provider' naming a "
                f"class as 'module:ClassName', got {provider!r}"
            )
        specs.append(
            HookSpec(
                provider=provider,
                kwargs={k: v for k, v in entry.items() if k != "provider"},
            )
        )
    return specs


def resolve_hooks(specs: Iterable[HookSpec]) -> list[object]:
    """Instantiate the provider each spec names, passing its remaining keys.

    Raises
    ------
    HookError
        If a provider path is malformed, names a module or attribute that does
        not exist, or names something that cannot be instantiated with the
        keys given.
    """
    return [instantiate(spec) for spec in specs]


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
