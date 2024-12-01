from redsun.controller.virtualbus import HardwareVirtualBus

def test_bus_singleton() -> None:
    """Tests that at creation, the virtual bus is a singleton."""
    bus1 = HardwareVirtualBus()
    bus2 = HardwareVirtualBus()
    assert bus1 is bus2

def test_bus_signals() -> None:
    """Tests that the virtual bus has the correct signals."""
    bus = HardwareVirtualBus()
    assert hasattr(bus, "sigStepperStepUp")
    assert hasattr(bus, "sigStepperStepDown")
    
    def test_slot(motor: str, axis: str) -> None:
        assert motor == "motor"
        assert axis == "axis"
    
    bus.sigStepperStepUp.connect(test_slot)
    bus.sigStepperStepUp.emit("motor", "axis")
    
    bus.sigStepperStepDown.connect(test_slot)
    bus.sigStepperStepDown.emit("motor", "axis")
    
