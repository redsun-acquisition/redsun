# ruff: noqa
"""Option 1: AppContainer compiles its declarations into a dishka Provider.

Author-facing view only. The machinery behind it is in `container_layer.py`.
Nothing here is executed: dishka is not installed in this environment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dishka import Provider, Scope, provide

from redsun.containers import declare_presenter, declare_view
from redsun.containers.qt import QtAppContainer
from redsun.presenter import Presenter
from redsun.storage import SessionPathProvider
from redsun.view.qt import QtView
from redsun.virtual import VirtualContainer, slot

if TYPE_CHECKING:
    from ophyd_async.core import Device
    from redsun.device import DeviceMap


class AcquisitionEngine:
    """Stand-in for something several components share."""


class Services(Provider):
    """Ordinary dishka provider. Nothing redsun-specific about it."""

    scope = Scope.APP

    @provide
    def path_provider(self, bus: VirtualContainer) -> SessionPathProvider:
        return SessionPathProvider(session=bus.session)

    @provide
    def engine(self, devices: DeviceMap) -> AcquisitionEngine:
        return AcquisitionEngine()


class StoragePresenter(Presenter):
    """No register_providers. The provider is a constructor parameter.

    `paths` is resolved by dishka. `max_digits` is not a dependency: it comes
    from the declaration or the config file, so the factory never offers it to
    the graph.
    """

    def __init__(
        self,
        name: str,
        /,
        paths: SessionPathProvider,
        max_digits: int = 5,
    ) -> None:
        super().__init__(name)
        self._paths = paths
        self._max_digits = max_digits

    @slot
    def set_plan(self, plan_name: str) -> None:
        self._paths.set_plan(plan_name)


class MotorPresenter(Presenter):
    """A presenter that does want the device map. It asks for it."""

    def __init__(
        self,
        name: str,
        /,
        devices: DeviceMap,
        engine: AcquisitionEngine,
        axis: str = "X",
    ) -> None:
        super().__init__(name)
        self._devices = devices
        self._engine = engine
        self._axis = axis


class StorageView(QtView):
    """`paths` is optional: nothing may provide it in a given application.

    The framework decides statically whether anything provides
    SessionPathProvider. If nothing does, None is bound into the factory and
    the parameter never reaches dishka.

    `bus` is the VirtualContainer, now an ordinary injectable. Because dishka
    has already resolved `paths`, the subscribe happens in __init__ rather
    than in a separate lifecycle hook.
    """

    def __init__(
        self,
        name: str,
        /,
        bus: VirtualContainer,
        paths: SessionPathProvider | None = None,
    ) -> None:
        super().__init__(name)
        if paths is None:
            self._placeholder()
            return
        self._paths = paths
        bus.subscribe(paths.signals.base_dir, self.update_base_dir)

    def _placeholder(self) -> None: ...

    @slot
    def update_base_dir(self, reading: dict[str, Any]) -> None: ...


class MyApp(QtAppContainer):
    """Declarative path. `declare_*` keeps its current signature and typing."""

    providers = [Services()]

    paths_ctrl = declare_presenter(StoragePresenter, max_digits=6)
    motor_x = declare_presenter(MotorPresenter, axis="X")
    motor_y = declare_presenter(MotorPresenter, axis="Y")
    storage_ui = declare_view(StorageView)

    def wire(self) -> None:
        # typed attribute access survives, so naming a signal the class does
        # not have is still an error before the build runs
        self.connect(self.paths_ctrl.sig_plan_set, self.storage_ui.update_base_dir)


# --------------------------------------------------------------------------
# Config-driven path: unchanged from the author's point of view.
#
#   session: my-session
#   frontend: pyqt
#   presenters:
#     paths_ctrl:
#       plugin_name: redsun
#       plugin_id: storage
#       max_digits: 6
#     motor_x:
#       plugin_name: my-plugin
#       plugin_id: motor
#       axis: X
#   views:
#     storage_ui:
#       plugin_name: redsun
#       plugin_id: storage_view
#   wiring:
#     - from: paths_ctrl.sig_plan_set
#       to: storage_ui.update_base_dir
#
# from_config() discovers the classes exactly as it does today, then registers
# one factory per YAML key instead of one _PresenterComponent per YAML key.
# The keys stay strings; NewType-per-name is what carries them into dishka.
#
# The only new obligation on a plugin author: services a plugin needs must be
# reachable. A plugin that ships its own dishka Provider declares it in its
# manifest, and from_config() collects those alongside the app's own.
#
#   # my_plugin/manifest.yaml
#   providers:
#     services: my_plugin.di:MyPluginServices
#   presenters:
#     motor: my_plugin.presenters:MotorPresenter
# --------------------------------------------------------------------------

app = MyApp.from_config("config.yaml")
app.build()
