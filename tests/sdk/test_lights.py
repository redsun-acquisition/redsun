"""Tests for the light presenter."""

from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING

import pytest
from ophyd_async.core import SignalRW, StandardReadable, soft_signal_rw

from redsun.presenter import DescribesLights, LightPresenter
from tests.sdk.mocks import BoundedBackend, DimmerLight, SoftLight

if TYPE_CHECKING:
    from collections.abc import Generator


class Detector(StandardReadable):
    """A device whose `enabled` is a number, not a light switch."""

    def __init__(self, name: str = "") -> None:
        self.enabled = soft_signal_rw(int, 1)
        super().__init__(name=name)


class GatedBackend(BoundedBackend):
    """A bounded intensity whose writes wait for `gate` and are recorded."""

    def __init__(self) -> None:
        super().__init__(0.0, 100.0, 10.0, "mW")
        self.gate = asyncio.Event()
        self.written: list[float] = []

    async def put(self, value: float | None) -> None:
        """Wait for the gate, record *value*, then write it."""
        await self.gate.wait()
        if value is not None:
            self.written.append(value)
        await super().put(value)


class SlowIntensity(SoftLight):
    """A light whose intensity writes wait for its backend's gate."""

    def __init__(self, name: str = "") -> None:
        self.backend = GatedBackend()
        with self.add_children_as_readables():
            self.intensity = SignalRW(self.backend)
        super().__init__(name)


@pytest.fixture
async def laser() -> DimmerLight:
    device = DimmerLight("laser")
    await device.connect(mock=False)
    return device


@pytest.fixture
async def led() -> SoftLight:
    device = SoftLight("led")
    await device.connect(mock=False)
    return device


@pytest.fixture
def presenter(
    laser: DimmerLight, led: SoftLight
) -> Generator[LightPresenter, None, None]:
    lights = LightPresenter("lights", devices={"laser": laser, "led": led})
    yield lights
    lights.shutdown()


async def test_lights_are_described_and_followed(
    presenter: LightPresenter, laser: DimmerLight
) -> None:
    """Describe each light, then relay what it reads back."""
    states: list[tuple[str, bool]] = []
    levels: list[tuple[str, float]] = []
    presenter.sig_enabled.connect(lambda *args: states.append(args))
    presenter.sig_intensity.connect(lambda *args: levels.append(args))

    await laser.enabled.set(True)
    await laser.intensity.set(42.0)

    assert isinstance(presenter, DescribesLights)
    assert presenter.lights["laser"].limits == (0.0, 100.0)
    assert presenter.lights["led"].intensity is None
    assert ("laser", True) in states
    assert ("laser", 42.0) in levels
    assert "laser-wavelength" in presenter.configuration.descriptors


async def test_switching_and_dimming_reach_the_light(
    presenter: LightPresenter, laser: DimmerLight
) -> None:
    """Switch a light on and set its intensity."""
    await presenter.set_enabled("laser", True)
    await presenter.set_intensity("laser", 55.0)

    assert await laser.enabled.get_value() is True
    assert await laser.intensity.get_value() == pytest.approx(55.0)


@pytest.mark.parametrize(
    ("device", "value"),
    [
        pytest.param("laser", 150.0, id="above"),
        pytest.param("laser", math.nan, id="not-finite"),
        pytest.param("led", 1.0, id="no-intensity"),
    ],
)
async def test_an_intensity_that_cannot_be_written_is_refused(
    presenter: LightPresenter, laser: DimmerLight, device: str, value: float
) -> None:
    """Refuse an intensity outside the limits, not finite, or for a light without one."""
    failures: list[tuple[str, str]] = []
    presenter.sig_failed.connect(lambda *args: failures.append(args))

    await presenter.set_intensity(device, value)

    assert await laser.intensity.get_value() == pytest.approx(10.0)
    assert [name for name, _ in failures] == [device]


async def test_a_held_light_takes_no_write(
    presenter: LightPresenter, laser: DimmerLight
) -> None:
    """Refuse switching or dimming a light a plan holds."""
    presenter.set_locked(frozenset({"laser"}))

    await presenter.set_enabled("laser", True)
    await presenter.set_intensity("laser", 50.0)

    assert await laser.enabled.get_value() is False
    assert await laser.intensity.get_value() == pytest.approx(10.0)


async def test_only_the_latest_intensity_follows_a_write_in_flight() -> None:
    """Write the newest of several intensities asked for during a slow write."""
    light = SlowIntensity("laser")
    await light.connect(mock=False)
    presenter = LightPresenter("lights", devices={"laser": light})

    first = asyncio.create_task(presenter.set_intensity("laser", 20.0))
    await asyncio.sleep(0)
    later = [
        asyncio.create_task(presenter.set_intensity("laser", value))
        for value in (30.0, 40.0, 50.0)
    ]
    await asyncio.sleep(0)
    light.backend.gate.set()
    await asyncio.gather(first, *later)

    assert light.backend.written == [20.0, 50.0]
    presenter.shutdown()


async def test_a_device_whose_enabled_is_not_a_switch_is_left_out(
    led: SoftLight,
) -> None:
    """Keep only devices whose `enabled` is a boolean signal."""
    detector = Detector("camera")
    await detector.connect(mock=False)

    presenter = LightPresenter(
        "lights",
        devices={"led": led, "camera": detector},  # type: ignore[dict-item]
    )

    assert set(presenter.lights) == {"led"}
    presenter.shutdown()


async def test_a_light_that_does_not_answer_is_left_out(
    led: SoftLight, caplog: pytest.LogCaptureFixture
) -> None:
    """Leave out a light that cannot be read in time, keeping the others."""
    stuck = SoftLight("stuck")
    await stuck.connect(mock=False)

    async def hang() -> bool:
        await asyncio.Event().wait()
        return False

    stuck.enabled.get_value = hang

    presenter = LightPresenter(
        "lights", devices={"led": led, "stuck": stuck}, timeout=0.2
    )

    assert set(presenter.lights) == {"led"}
    assert "Leaving out stuck" in caplog.text
    presenter.shutdown()
