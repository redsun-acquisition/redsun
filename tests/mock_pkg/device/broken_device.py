from sunflare.device import Device

class BrokenDevice(Device):
    def __init__(self, name: str) -> None:
        raise ValueError("This device is broken")
