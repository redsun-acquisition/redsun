from collections.abc import Mapping

import pytest
from ophyd_async.core import Device

from redsun.presenter import PPresenter, Presenter
from redsun.virtual import IsInjectable, IsProvider, VirtualContainer


@pytest.fixture
def devices() -> dict[str, Device]:
    return {}


def test_base_presenter(devices: Mapping[str, Device]) -> None:
    """Test basic Presenter functionality."""

    class TestController(Presenter):
        def __init__(
            self,
            name: str,
            devices: Mapping[str, Device],
        ) -> None:
            super().__init__(name, devices)

    controller = TestController("ctrl", devices)

    assert controller.name == "ctrl"
    assert controller.devices == devices


def test_presenter_is_provider(
    devices: Mapping[str, Device], bus: VirtualContainer
) -> None:
    """Test that a presenter can optionally implement IsProvider."""

    class ProviderController(Presenter):
        def __init__(
            self,
            name: str,
            devices: Mapping[str, Device],
        ) -> None:
            super().__init__(name, devices)

        def register_providers(self, container: VirtualContainer) -> None:
            pass  # would register DI providers here

    controller = ProviderController("ctrl", devices)
    assert isinstance(controller, IsProvider)
    assert issubclass(ProviderController, IsProvider)
    controller.register_providers(bus)


def test_presenter_is_injectable(
    devices: Mapping[str, Device], bus: VirtualContainer
) -> None:
    """Test that a presenter can be registered as a provider in the virtual container."""

    class InjectableController(Presenter):
        def __init__(
            self,
            name: str,
            devices: Mapping[str, Device],
        ) -> None:
            super().__init__(name, devices)

        def inject_dependencies(self, container: VirtualContainer) -> None:
            pass  # would inject dependencies here

    controller = InjectableController("ctrl", devices)
    assert isinstance(controller, Presenter)
    assert isinstance(controller, IsInjectable)
    assert issubclass(InjectableController, IsInjectable)


class _PropertyPresenter:
    """Structural presenter using read-only properties - no ABC involved."""

    def __init__(self, name: str, devices: Mapping[str, Device], /) -> None:
        self._name = name
        self._devices = dict(devices)

    @property
    def name(self) -> str:
        return self._name

    @property
    def devices(self) -> Mapping[str, Device]:
        return self._devices


def test_property_based_presenter_satisfies_protocol(
    devices: Mapping[str, Device],
) -> None:
    """Read-only protocol members accept property-based implementers."""
    presenter: PPresenter = _PropertyPresenter("p", devices)  # static check
    assert isinstance(presenter, PPresenter)  # runtime check


def test_dict_devices_satisfies_protocol() -> None:
    """dict[str, Device] is covariantly accepted by the read-only member."""

    class _DictPresenter:
        def __init__(self) -> None:
            self.name = "d"
            self.devices: dict[str, Device] = {}

    presenter: PPresenter = _DictPresenter()  # static check
    assert isinstance(presenter, PPresenter)


def test_abc_instances_satisfy_protocol(devices: Mapping[str, Device]) -> None:
    """The convenience ABC satisfies the protocol structurally, not nominally."""

    class _Concrete(Presenter):
        def __init__(self, name: str, devices: Mapping[str, Device], /) -> None:
            super().__init__(name, devices)

    instance = _Concrete("c", devices)
    presenter: PPresenter = instance  # static check
    assert isinstance(presenter, PPresenter)
    assert PPresenter not in type(instance).__mro__
