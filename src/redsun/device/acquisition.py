from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """String-valued enum compatible with Python 3.11's StrEnum."""


from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from bluesky.protocols import StreamAsset, SyncOrAsync, SyncOrAsyncIterator
    from event_model import DataKey

T_contra = TypeVar("T_contra", contravariant=True)


class TriggerType(StrEnum):
    """Hardware trigger modes for acquisition devices.

    Attributes
    ----------
    INTERNAL:
        The device generates its own trigger at a fixed rate.
    EDGE_TRIGGER:
        An external signal edge starts each exposure; exposure
        length is determined by the device settings.
    CONSTANT_GATE:
        An external gate signal of constant width controls each
        exposure; width equals the requested livetime.
    VARIABLE_GATE:
        An external gate signal of variable width controls each
        exposure; the device follows the gate duration.
    """

    INTERNAL = "internal"
    EDGE_TRIGGER = "edge_trigger"
    CONSTANT_GATE = "constant_gate"
    VARIABLE_GATE = "variable_gate"


@runtime_checkable
class TriggerInfo(Protocol):
    """Trigger configuration passed to an acquisition device at prepare time.

    Structurally compatible with ``ophyd_async.core.TriggerInfo``.

    Attributes
    ----------
    number_of_events:
        Number of events (frame groups) to acquire.  A list is accepted
        for multi-step scans where each element is the count for one
        ``kickoff``/``complete`` pair (e.g. dark, flat, projection
        sequences in tomography).
    trigger:
        Hardware trigger mode. See :class:`TriggerType`.
    deadtime:
        Minimum dead time between exposures in seconds.  Required when
        ``trigger`` is anything other than :attr:`TriggerType.INTERNAL`.
    livetime:
        Requested exposure duration in seconds, or ``None`` to use the
        device default.
    exposures_per_event:
        Number of hardware exposures that constitute one logical event
        (reading). Defaults to 1. Useful when multiple frames must be
        averaged or accumulated before emitting a document.
    """

    number_of_events: int | list[int]
    trigger: TriggerType
    deadtime: float
    livetime: float | None
    exposures_per_event: int


@runtime_checkable
class AcquisitionController(Protocol):
    """Hardware-side acquisition logic.

    Responsible for arming, triggering, and disarming the physical
    device.  Completely decoupled from data persistence.

    Structurally compatible with ``ophyd_async.core.DetectorController``.
    """

    def get_deadtime(self, exposure: float | None) -> float:
        """Return the minimum dead time for a given exposure duration.

        This method must be **state-independent**: the returned value may
        only depend on the ``exposure`` argument and static device
        constants known at construction time (e.g. sensor readout time,
        firmware processing overhead, communication latency).  It must
        never read a signal, perform I/O, or inspect live device state.

        This constraint is why the return type is a plain ``float`` and
        not ``SyncOrAsync[float]``.  The method is called during
        ``prepare`` validation — potentially before the device is armed
        or a hardware connection is confirmed — so no I/O can be assumed
        to be available.

        The value is used by the acquisition orchestrator to fill in
        ``TriggerInfo.deadtime`` when it is unset and the trigger mode
        is external, ensuring that external triggers are spaced safely.

        Parameters
        ----------
        exposure:
            Requested exposure duration in seconds, or ``None`` if
            unspecified by the scan.

        Returns
        -------
        float
            Minimum dead time in seconds between consecutive exposures.
        """
        ...

    def prepare(self, trigger_info: TriggerInfo) -> SyncOrAsync[None]:
        """Configure the device for the upcoming acquisition.

        Called once before the first :meth:`arm` of a scan.

        Parameters
        ----------
        trigger_info:
            Trigger configuration for the scan.
        """
        ...

    def arm(self) -> SyncOrAsync[None]:
        """Start acquisition.

        For internally-triggered devices this is called at ``kickoff``.
        For externally-triggered devices this is called at ``prepare``
        so that the device is ready to accept triggers immediately.
        """
        ...

    def wait_for_idle(self) -> SyncOrAsync[None]:
        """Block until the device has finished all pending acquisitions.

        Called after the final ``complete`` of a scan.
        """
        ...

    def disarm(self) -> SyncOrAsync[None]:
        """Stop acquisition and return the device to an idle state."""
        ...


@runtime_checkable
class AcquisitionWriter(Protocol):
    """Persistence-side acquisition logic.

    Responsible for opening storage, monitoring write progress, emitting
    stream documents, and closing storage.  Completely decoupled from
    hardware control.

    Structurally compatible with ``ophyd_async.core.DetectorWriter``.
    """

    def open(
        self,
        name: str,
        exposures_per_event: int = 1,
    ) -> SyncOrAsync[dict[str, DataKey]]:
        """Open storage and return the ``describe()`` output.

        Parameters
        ----------
        name:
            Canonical device name used as the data key prefix.
        exposures_per_event:
            Number of hardware exposures per logical event.

        Returns
        -------
        SyncOrAsync[dict[str, DataKey]]
            Bluesky data-key descriptors for the written datasets.
        """
        ...

    def observe_indices_written(
        self,
        timeout: float,
    ) -> SyncOrAsyncIterator[int]:
        """Yield the running count of completed events as they are written.

        This is the heartbeat used by ``complete()`` to track progress.
        Each yielded integer is the total number of events written so far.
        A sync implementation blocks between yields; an async one awaits.

        Parameters
        ----------
        timeout:
            Maximum time in seconds to wait for the next index before
            raising a timeout error.
        """
        ...

    def collect_stream_docs(
        self,
        name: str,
        indices_written: int,
    ) -> SyncOrAsyncIterator[StreamAsset]:
        """Yield ``StreamResource`` and ``StreamDatum`` documents.

        Called by ``collect_asset_docs`` to produce the bluesky documents
        that describe the written data for the current scan step.

        Parameters
        ----------
        name:
            Canonical device name.
        indices_written:
            Number of events written up to this point.
        """
        ...

    def close(self) -> SyncOrAsync[None]:
        """Finalise and close storage."""
        ...


@runtime_checkable
class FlyerController(Protocol[T_contra]):
    """Motion-based trigger logic for fly scans.

    Encapsulates the motion and trigger sequencing for a fly scan,
    keeping it decoupled from any specific detector.

    Structurally compatible with ``ophyd_async.core.FlyerController``.

    Type Parameters
    ---------------
    T_contra:
        The type of the value accepted by :meth:`prepare` — typically
        a scan-path or sequencer-table description.  Contravariant
        because it only appears in input position.
    """

    def prepare(self, value: T_contra) -> SyncOrAsync[None]:
        """Move to the scan start position and configure triggers.

        Parameters
        ----------
        value:
            Scan configuration (path, table, etc.).
        """
        ...

    def kickoff(self) -> SyncOrAsync[None]:
        """Start motion and trigger emission."""
        ...

    def complete(self) -> SyncOrAsync[None]:
        """Block until motion and all triggers are done."""
        ...

    def stop(self) -> SyncOrAsync[None]:
        """Abort motion and clean up."""
        ...
