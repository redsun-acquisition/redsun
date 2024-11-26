from redsun.controller.virtualbus import HardwareVirtualBus

def test_bus_singleton() -> None:
    """Tests that at creation, the virtual bus is a singleton."""
    bus1 = HardwareVirtualBus.instance()
    bus2 = HardwareVirtualBus.instance()
    assert bus1 is bus2
