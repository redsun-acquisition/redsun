import pytest
from collections.abc import Mapping
from redsun.device import Device
from redsun.presenter import Presenter
from redsun.virtual import VirtualContainer, IsProvider, IsInjectable


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
