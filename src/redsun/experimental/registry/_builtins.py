from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TypeAlias

from event_model import DocumentRouter
from event_model.documents import Document
from ophyd_async.core import Device

__all__ = [
    "CallbackType",
    "DeviceMapping",
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
