"""ophyd-async mock devices for container integration tests."""

from ophyd_async.core import StandardReadable, soft_signal_rw


class MockOAMotor(StandardReadable):
    """Mock motor device implemented as an ophyd-async ``StandardReadable``.

    Implements the ophyd-async ``Device`` interface via ``StandardReadable``
    (provides ``name``, ``parent``, ``read_configuration``,
    ``describe_configuration``).

    Signals must be connected (``await device.connect(mock=True)``) before
    their values can be read.
    """

    def __init__(self, name: str, /, *, units: str = "mm") -> None:
        self.x = soft_signal_rw(float, units=units)
        self.y = soft_signal_rw(float, units=units)
        super().__init__(name=name)
