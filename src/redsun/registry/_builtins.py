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

    from redsun.engine.actions import ActionManager

__all__ = [
    "CallbackType",
    "DeviceMapping",
    "HasActions",
    "HasPlans",
    "PlanEntry",
    "SessionConfig",
]

# these three are dependency keys, so every name in them must resolve at runtime:
# the graph evaluates the annotation, and a TYPE_CHECKING-only import fails there
CallbackType: TypeAlias = Callable[[str, Document], None] | DocumentRouter
"""A document callback: a `DocumentRouter`, or anything callable as `(name, doc)`."""

DeviceMapping: TypeAlias = Mapping[str, Device]
"""Every device an application built, by name.

Not ophyd-async's `DeviceMap`, which is a device holding string-keyed
children; this is the application's own set.
"""


@dataclass(frozen=True, kw_only=True)
class SessionConfig:
    """The configuration an application was built from."""

    schema_version: float = 1.0
    """Format of the session file."""

    frontend: str | None = None
    """Registered name of the frontend the session is built on, if any."""

    session: str = "Redsun"
    """Name of the session."""

    mock: bool = False
    """Whether the devices connect to simulated backends and no service starts."""

    metadata: dict[str, object] = field(default_factory=dict)
    """What the session file asks to have recorded with the session."""


class PlanEntry(TypedDict, total=False):
    """A plan a component offers, and the document callbacks it requires.

    Only `plan` is required.
    """

    plan: Required[Callable[..., MsgGenerator[Any]]]
    """The plan, a generator function."""

    callbacks: Sequence[CallbackType]
    """Callbacks the plan requires, run in this order before any a user attaches."""

    extendable: bool
    """Whether a user may attach callbacks. `True` when absent."""


@runtime_checkable
class HasActions(Protocol):
    """A component whose plans offer actions to take while they run."""

    @property
    def actions(self) -> ActionManager:
        """The actions of the component's plans."""
        ...


@runtime_checkable
class HasPlans(Protocol):
    """A component offering plans."""

    def plan_map(self) -> Mapping[str, PlanEntry]:
        """Return the plans this component offers, by plan name."""
