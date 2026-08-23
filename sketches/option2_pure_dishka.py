# ruff: noqa
"""Option 2: components are declared as dishka Providers. `declare_*` is gone.

Most idiomatic dishka, least redsun. Shown to make the losses concrete.
Nothing here is executed: dishka is not installed in this environment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NewType

from dishka import Provider, Scope, make_container, provide

from redsun.presenter import Presenter
from redsun.storage import SessionPathProvider
from redsun.view.qt import QtView
from redsun.virtual import VirtualContainer, slot

if TYPE_CHECKING:
    from redsun.device import DeviceMap


# multiplicity is the author's problem now: two instances of one class means
# two NewTypes, hand-written, and every consumer must name the right one
MotorX = NewType("MotorX", "MotorPresenter")
MotorY = NewType("MotorY", "MotorPresenter")


class MotorPresenter(Presenter):
    def __init__(self, name: str, devices: DeviceMap, axis: str) -> None:
        super().__init__(name)


class StoragePresenter(Presenter):
    def __init__(self, name: str, paths: SessionPathProvider) -> None:
        super().__init__(name)

    @slot
    def set_plan(self, plan_name: str) -> None: ...


class StorageView(QtView):
    def __init__(self, name: str, bus: VirtualContainer) -> None:
        super().__init__(name)

    @slot
    def update_base_dir(self, reading: dict[str, object]) -> None: ...


class AppProvider(Provider):
    scope = Scope.APP

    @provide
    def paths(self, bus: VirtualContainer) -> SessionPathProvider:
        return SessionPathProvider(session=bus.session)

    @provide
    def paths_ctrl(self, paths: SessionPathProvider) -> StoragePresenter:
        return StoragePresenter("paths_ctrl", paths)

    @provide
    def motor_x(self, devices: DeviceMap) -> MotorX:
        return MotorX(MotorPresenter("motor_x", devices, axis="X"))

    @provide
    def motor_y(self, devices: DeviceMap) -> MotorY:
        return MotorY(MotorPresenter("motor_y", devices, axis="Y"))

    @provide
    def storage_ui(self, bus: VirtualContainer) -> StorageView:
        return StorageView("storage_ui", bus)


def main() -> None:
    di = make_container(AppProvider(), FrameworkProvider())

    # every component must be named twice: once as a factory method, once here
    paths_ctrl = di.get(StoragePresenter)
    storage_ui = di.get(StorageView)
    bus = di.get(VirtualContainer)

    bus.connect(paths_ctrl.sig_plan_set, storage_ui.update_base_dir)


# What this costs, concretely:
#
# 1. `wire()` stops being checked at declaration. There is no `self.paths_ctrl`
#    typed as StoragePresenter, so a mistyped signal name is found at runtime.
# 2. The component name is a string literal repeated inside every factory, and
#    nothing keeps it in sync with the name used in wiring paths.
# 3. from_config() has nowhere to land. A YAML file cannot add a @provide
#    method; you would generate Provider subclasses at runtime, which is
#    Option 1 wearing a different hat but without the typed attributes.
# 4. Config kwargs (`axis="X"`, `max_digits=6`) are frozen into source. Today
#    they come from the config file per named instance.
# 5. Multiplicity is manual: NewType per instance, written out, and every
#    consumer must pick the right one by name.
#
# Point 3 is the fatal one for a config-driven acquisition app.
