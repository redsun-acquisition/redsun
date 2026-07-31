"""Tests for `redsun.presenter.builtins.StoragePresenter`.

Also the evaluation ground for the two path-provider access approaches:

- **(a) storage-attached:** ``BaseStorage.path_provider`` property, reached
  through the storage registry (``get_storage(group, mimetype).path_provider``).
- **(b) DI-attached:** the provider registered on the `VirtualContainer` as
  the ``path_provider`` DI provider by `StoragePresenter.register_providers`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
import pytest
from psygnal import Signal

from redsun.presenter.builtins import StoragePresenter
from redsun.storage import (
    PATH_PROVIDER,
    BaseStorage,
    SessionPathProvider,
    StreamSpec,
    clear_registry,
    get_storage,
    register_storage,
)
from redsun.storage.backends._memory import MemoryIO

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from redsun.virtual import VirtualContainer


class _AcquisitionSignals:
    """Stand-in for an acquisition presenter's plan lifecycle signals."""

    sig_pre_launch_notify = Signal(str)
    sig_plan_done = Signal()

    def __init__(self) -> None:
        self.name = "acquisition"


@pytest.fixture
def configured_bus(bus: VirtualContainer) -> VirtualContainer:
    bus._set_configuration(
        {"schema_version": 1.0, "frontend": "pyqt", "session": "unit-session"}
    )
    return bus


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    clear_registry()
    yield
    clear_registry()


def test_provider_unavailable_before_register_providers(tmp_path: Path) -> None:
    presenter = StoragePresenter("storage", {}, base_dir=str(tmp_path))
    with pytest.raises(RuntimeError, match="register_providers"):
        _ = presenter.path_provider


def test_register_providers_creates_session_scoped_provider(
    configured_bus: VirtualContainer, tmp_path: Path
) -> None:
    presenter = StoragePresenter("storage", {}, base_dir=str(tmp_path))
    presenter.register_providers(configured_bus)

    provider = configured_bus.require(PATH_PROVIDER)
    assert provider is presenter.path_provider
    info = provider()
    date = datetime.now().strftime("%Y-%m-%d")
    assert info.directory_path == tmp_path / "unit-session" / date
    assert info.filename == "unknown_00000"


async def test_plan_signals_drive_filenames(
    configured_bus: VirtualContainer, tmp_path: Path
) -> None:
    presenter = StoragePresenter("storage", {}, base_dir=str(tmp_path))
    presenter.register_providers(configured_bus)
    acquisition = _AcquisitionSignals()
    configured_bus.register_signals(acquisition)
    presenter.inject_dependencies(configured_bus)

    acquisition.sig_pre_launch_notify.emit("square_scan")
    assert await presenter.path_provider.signals.plan.get_value() == "square_scan"
    assert presenter.path_provider().filename == "square_scan_00000"

    acquisition.sig_plan_done.emit()
    assert await presenter.path_provider.signals.plan.get_value() == "unknown"


async def test_approach_di_container_wires_storage_bursts(
    configured_bus: VirtualContainer, tmp_path: Path
) -> None:
    """Approach (b): consumers resolve the provider from the DI container.

    The presenter owns the provider; a downstream component (whatever builds
    the application's `BaseStorage` instances) resolves ``path_provider``
    from the container and hands it to the storage constructor. Plan-name
    changes made through the presenter's signal wiring show up in the burst
    paths without the storage ever knowing who controls them.
    """
    presenter = StoragePresenter("storage", {}, base_dir=str(tmp_path))
    presenter.register_providers(configured_bus)
    acquisition = _AcquisitionSignals()
    configured_bus.register_signals(acquisition)
    presenter.inject_dependencies(configured_bus)

    provider = configured_bus.require(PATH_PROVIDER)
    io = MemoryIO()
    storage = BaseStorage(io=io, path_provider=provider)

    acquisition.sig_pre_launch_notify.emit("scan")
    storage.register(
        StreamSpec(data_key="det", shape=(4, 4), dtype="uint16", capacity=1)
    )
    sink = storage.sink("det")
    await sink.put(np.zeros((4, 4), dtype=np.uint16))
    await storage.close()

    assert io.stores[0].path.filename == "scan_00000"


def test_approach_storage_property_via_registry(tmp_path: Path) -> None:
    """Approach (a): the provider is reached through the storage instance.

    ``get_storage(group, mimetype).path_provider`` works, but the consumer
    must know a (group, mimetype) pair - storage-layer coordinates - to
    reach an application-scoped object. Kept for evaluation against the
    DI approach above.
    """
    provider = SessionPathProvider(base_dir=tmp_path, session="s")
    storage = BaseStorage(io=MemoryIO(), path_provider=provider)
    assert storage.path_provider is provider

    register_storage("acq", storage)
    assert get_storage("acq", storage.mimetype).path_provider is provider
