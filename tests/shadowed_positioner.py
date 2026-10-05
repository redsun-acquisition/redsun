"""A positioner subclass declared where `DeviceMapping` names something else."""

from __future__ import annotations

from dataclasses import dataclass

from redsun.presenter import PositionerPresenter

DeviceMapping = int
"""Unrelated to the session's device mapping, under the same name."""


@dataclass(eq=False, kw_only=True)
class ShadowedPositioner(PositionerPresenter):
    """A positioner with a field of its own, in a module shadowing a base type."""

    note: str = ""
