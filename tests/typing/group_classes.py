"""A view's `group_class` takes only a widget class built the way the view builds it.

Never imported or executed; checked by the project's normal mypy invocation. A
subclass whose constructor differs must be refused where it is named, since
the view calls it in `setup` with its own arguments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from redsun.view.qt.builtins import (
    LightGroup,
    LightView,
    PositionerGroup,
    PositionerView,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qtpy import QtWidgets


class LabelledGroup(PositionerGroup):
    def __init__(self, device: str, axes: Mapping[str, Any], **options: Any) -> None:
        super().__init__(device, axes, **options)


class DeviceOnlyGroup(PositionerGroup):
    def __init__(self, device: str) -> None:
        super().__init__(device, {}, steps=[1.0], repeat_delay=0, repeat_interval=0)


class DeviceOnlyLight(LightGroup):
    def __init__(self, device: str, parent: QtWidgets.QWidget | None = None) -> None:
        raise NotImplementedError


class LabelledView(PositionerView):
    group_class = LabelledGroup


class BrokenView(PositionerView):
    group_class = DeviceOnlyGroup  # type: ignore[assignment]


class BrokenLightView(LightView):
    group_class = DeviceOnlyLight  # type: ignore[assignment]
