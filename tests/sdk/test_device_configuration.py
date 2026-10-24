"""Tests for reading, following and writing device configuration."""

from __future__ import annotations

import pytest
from ophyd_async.core import Device

from redsun.presenter import DeviceConfiguration
from redsun.utils.devices import device_path
from tests.sdk.mocks import SoftAxis, XYStage


class Rig(Device):
    """A root holding a stage with the axes `x` and `y`."""

    def __init__(self, name: str = "") -> None:
        self.xy = XYStage("")
        super().__init__(name=name)


@pytest.fixture
async def axis() -> SoftAxis:
    """Return a connected soft axis named `focus`."""
    device = SoftAxis("focus")
    await device.connect(mock=False)
    return device


@pytest.fixture
async def rig() -> Rig:
    """Return a connected rig named `scope`."""
    device = Rig("scope")
    await device.connect(mock=False)
    return device


async def test_a_device_is_read_followed_and_written(axis: SoftAxis) -> None:
    """Read a device's configuration, report changes made on it, and write it."""
    configuration = DeviceConfiguration("lights")
    seen: list[tuple[str, object]] = []
    configuration.sig_changed.connect(lambda *args: seen.append(args))

    added = await configuration.add("focus", axis)
    seen.clear()
    axis.set_resolution(0.5)
    owner = await configuration.configure(axis.velocity.name, 3.0)

    assert set(added.descriptors) == {axis.velocity.name, axis.resolution.name}
    assert configuration.configuration.writable == {axis.velocity.name: axis.velocity}
    assert owner == "focus"
    assert (axis.resolution.name, 0.5) in seen
    assert seen[-1] == (axis.velocity.name, 3.0)


async def test_a_held_owner_is_not_written_but_read_back(axis: SoftAxis) -> None:
    """Refuse a write to a held owner's key, still reporting its value."""
    configuration = DeviceConfiguration("lights")
    await configuration.add("focus", axis)
    seen: list[tuple[str, object]] = []
    configuration.sig_changed.connect(lambda *args: seen.append(args))

    configuration.set_locked(frozenset({"focus"}))
    await configuration.configure(axis.velocity.name, 9.0)

    assert await axis.velocity.get_value() == pytest.approx(1.0)
    assert seen == [(axis.velocity.name, 1.0)]


@pytest.mark.parametrize(
    "key", ["focus-resolution", "no-such-key"], ids=["read-only", "unknown"]
)
async def test_an_unknown_or_read_only_key_is_refused(axis: SoftAxis, key: str) -> None:
    """Raise `KeyError` for a key that names no writable configuration signal."""
    configuration = DeviceConfiguration("lights")
    await configuration.add("focus", axis)

    with pytest.raises(KeyError):
        await configuration.configure(key, 1.0)


async def test_nothing_is_followed_after_remove_all(axis: SoftAxis) -> None:
    """Report no change once every subscription is removed."""
    configuration = DeviceConfiguration("lights")
    await configuration.add("focus", axis)
    seen: list[tuple[str, object]] = []
    configuration.sig_changed.connect(lambda *args: seen.append(args))

    configuration.remove_all()
    await axis.velocity.set(4.0)

    assert seen == []


async def test_a_failing_receiver_does_not_reach_the_device(
    axis: SoftAxis, caplog: pytest.LogCaptureFixture
) -> None:
    """Log a receiver that raises on a change, leaving the device's write alone."""
    configuration = DeviceConfiguration("lights")
    await configuration.add("focus", axis)

    def fail(*args: object) -> None:
        raise RuntimeError("receiver broke")

    configuration.sig_changed.connect(fail)
    await axis.velocity.set(3.0)

    assert "Relaying a configuration value" in caplog.text


async def test_each_key_is_filed_under_its_owner(axis: SoftAxis) -> None:
    """Record the owner of every key, whatever the device's own name."""
    configuration = DeviceConfiguration("lights")

    await configuration.add("focus-488", axis)

    assert set(configuration.configuration.owners.values()) == {"focus-488"}


async def test_configuration_paths_name_each_key_and_its_owner(rig: Rig) -> None:
    """Give each configuration key and its owner their place in the tree."""
    configuration = DeviceConfiguration("positioner")

    added = await configuration.add("scope-xy", rig.xy.x, owner_device=rig.xy)

    assert added.paths["scope-xy-x-velocity"].path == "xy.x.velocity"
    assert configuration.configuration.paths["scope-xy"] == device_path(rig.xy)


async def test_a_write_below_a_held_device_is_refused(rig: Rig) -> None:
    """Refuse a configuration write when a device above the signal is held."""
    configuration = DeviceConfiguration("positioner")
    await configuration.add("scope-xy", rig.xy.x, owner_device=rig.xy)

    configuration.set_locked(frozenset({"scope-xy-x"}))
    await configuration.configure("scope-xy-x-velocity", 3.0)

    assert await rig.xy.x.velocity.get_value() == pytest.approx(1.0)


async def test_holding_an_unknown_name_holds_nothing(rig: Rig) -> None:
    """Write as usual when the held names match no device of the configuration."""
    configuration = DeviceConfiguration("positioner")
    await configuration.add("scope-xy", rig.xy.x, owner_device=rig.xy)

    configuration.set_locked(frozenset({"elsewhere"}))
    await configuration.configure("scope-xy-x-velocity", 3.0)

    assert await rig.xy.x.velocity.get_value() == pytest.approx(3.0)


async def test_a_key_added_twice_is_followed_once(rig: Rig) -> None:
    """Relay each change of a signal once and keep its first owner when added again."""
    configuration = DeviceConfiguration("lights")
    await configuration.add("scope-xy", rig.xy.x, owner_device=rig.xy)
    await configuration.add("scope-xy-x", rig.xy.x)
    seen: list[tuple[str, object]] = []
    configuration.sig_changed.connect(lambda *args: seen.append(args))

    await rig.xy.x.velocity.set(3.0)

    assert seen == [("scope-xy-x-velocity", 3.0)]
    assert configuration.configuration.owners["scope-xy-x-velocity"] == "scope-xy"
