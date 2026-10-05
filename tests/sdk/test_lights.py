"""Tests for the light presenter."""

from __future__ import annotations

import asyncio
import math
from concurrent.futures import CancelledError
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from ophyd_async.core import SignalRW, StandardReadable, set_mock_attr, soft_signal_rw

from redsun.presenter import DescribesLights, LightPresenter
from tests.sdk.mocks import BoundedBackend, DimmerLight, SoftLight, WholeLight

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
    laser_intensity = presenter.lights["laser"].intensity
    assert laser_intensity is not None
    assert laser_intensity.limits == (0.0, 100.0)
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


async def test_a_queued_intensity_is_dropped_once_a_plan_holds_the_light() -> None:
    """Write nothing more to a light a plan takes while an intensity waits."""
    light = SlowIntensity("laser")
    await light.connect(mock=False)
    presenter = LightPresenter("lights", devices={"laser": light})

    first = asyncio.create_task(presenter.set_intensity("laser", 20.0))
    await asyncio.sleep(0)
    queued = asyncio.create_task(presenter.set_intensity("laser", 50.0))
    await asyncio.sleep(0)
    presenter.set_locked(frozenset({"laser"}))
    light.backend.gate.set()
    await asyncio.gather(first, queued)

    assert light.backend.written == [20.0]
    presenter.shutdown()


async def test_a_write_that_fails_is_reported(presenter: LightPresenter) -> None:
    """Report a write the light refuses on `sig_failed`."""
    failures: list[tuple[str, str]] = []
    presenter.sig_failed.connect(lambda *args: failures.append(args))
    light = presenter.devices["laser"]

    async def refuse(
        value: bool, wait: bool = True, timeout: float | None = None
    ) -> None:
        raise RuntimeError("interlock open")

    set_mock_attr(light.enabled, "set", refuse)
    await presenter.set_enabled("laser", True)

    assert failures == [("laser", "interlock open")]


async def test_a_cancelled_start_leaves_no_light_followed() -> None:
    """Follow no light once the start is cancelled while one is being read."""
    light = DimmerLight("laser")
    await light.connect(mock=False)

    async def cancelled() -> dict[str, object]:
        raise asyncio.CancelledError

    set_mock_attr(light, "read_configuration", cancelled)
    built: list[LightPresenter] = []

    @dataclass(eq=False, kw_only=True)
    class Remembered(LightPresenter):
        """A light presenter that keeps every instance it starts to build."""

        def __post_init__(self) -> None:
            """Remember this instance, then build it."""
            built.append(self)
            super().__post_init__()

    with pytest.raises(CancelledError):
        Remembered("lights", devices={"laser": light})
    seen: list[tuple[str, bool]] = []
    built[0].sig_enabled.connect(lambda *args: seen.append(args))

    await light.enabled.set(True)

    assert seen == []


async def test_an_included_name_that_is_no_light_is_reported(
    led: SoftLight, caplog: pytest.LogCaptureFixture
) -> None:
    """Warn about included names with no `enabled` signal or a non-boolean one."""
    detector = Detector("camera")
    await detector.connect(mock=False)

    presenter = LightPresenter(
        "lights",
        devices={"led": led, "camera": detector},  # type: ignore[dict-item]
        include=["led", "camera", "ghost"],
    )

    assert "No device named ghost has an `enabled` signal" in caplog.text
    assert "camera is left out: its `enabled` is not a boolean signal" in caplog.text
    presenter.shutdown()


async def test_a_whole_number_intensity_is_written_whole_and_without_limits() -> None:
    """Write a whole number to an integer intensity, however large, with no limits."""
    lamp = WholeLight("lamp")
    await lamp.connect(mock=False)
    presenter = LightPresenter("lights", devices={"lamp": lamp})

    await presenter.set_intensity("lamp", 1_000_000.0)

    value = await lamp.intensity.get_value()
    assert (value, type(value)) == (1_000_000, int)
    lamp_intensity = presenter.lights["lamp"].intensity
    assert lamp_intensity is not None
    assert lamp_intensity.precision == 0
    presenter.shutdown()
