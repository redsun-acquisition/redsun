from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    Required,
    TypeAlias,
    TypedDict,
    runtime_checkable,
)

from event_model import DocumentRouter
from event_model.documents import Document
from ophyd_async.core import Device

if TYPE_CHECKING:
    from bluesky.utils import MsgGenerator

__all__ = [
    "CallbackType",
    "DeviceMapping",
    "HasPlans",
    "PlanEntry",
    "SessionConfig",
]

# these three are dependency keys, so every name in them must resolve at runtime:
# the graph evaluates the annotation, and a TYPE_CHECKING-only import fails there
CallbackType: TypeAlias = Callable[[str, Document], None] | DocumentRouter
"""A document callback: a `DocumentRouter`, or anything callable as ``(name, doc)``."""

DeviceMapping: TypeAlias = Mapping[str, Device]
"""Every device an application built, by name.

Not ophyd-async's ``DeviceMap``, which is a device holding string-keyed
children; this is the application's own set.
"""

"""The signals one component declares, by attribute name."""


@dataclass(frozen=True, kw_only=True)
class SessionConfig:
    """The configuration an application was built from."""

    schema_version: float = 1.0
    frontend: str = "pyqt"
    name: str = "Redsun"
    metadata: dict[str, object] = field(default_factory=dict)


class PlanEntry(TypedDict, total=False):
    """A plan a component offers, and the document callbacks it requires.

    ``callbacks`` run in the order given, before any callback a user attaches.
    ``extendable`` is whether a user may attach any, and is ``True`` when
    absent. Only ``plan`` is required.
    """

    plan: Required[Callable[..., MsgGenerator[Any]]]
    callbacks: Sequence[CallbackType]
    extendable: bool


@runtime_checkable
class HasPlans(Protocol):
    """A component offering plans."""

    def plan_map(self) -> Mapping[str, PlanEntry]:
        """Return the plans this component offers, by plan name."""
