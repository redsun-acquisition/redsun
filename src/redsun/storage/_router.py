from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ophyd_async.core import soft_signal_r_and_setter

if TYPE_CHECKING:
    from collections.abc import Callable

    from ophyd_async.core import SignalR

    from ._base import StreamSpec


@dataclass(slots=True)
class FrameRouter:
    """Router for managing streams and their frame counters."""

    _specs: dict[str, StreamSpec] = field(default_factory=dict, init=False, repr=False)
    _indeces: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _signals: dict[str, SignalR[int]] = field(
        default_factory=dict, init=False, repr=False
    )
    _setters: dict[str, Callable[[int], None]] = field(
        default_factory=dict, init=False, repr=False
    )

    @property
    def spec(self) -> dict[str, StreamSpec]:
        """Map of data keys to their StreamSpec objects."""
        return self._specs

    @property
    def signals(self) -> dict[str, SignalR[int]]:
        """Map of data keys to signals that track the number of frames written for each key."""
        return self._signals

    def add(self, spec: StreamSpec) -> None:
        """Add a new spec and initialize its frame counter."""
        if spec.data_key in self._specs.keys():
            raise KeyError(f"Key '{spec.data_key!r}' is already routed.")
        signal, setter = soft_signal_r_and_setter(int, initial_value=0)
        self._specs[spec.data_key] = spec
        self._indeces[spec.data_key] = 0
        self._signals[spec.data_key] = signal
        self._setters[spec.data_key] = setter

    def pop(self, data_key: str) -> None:
        """Remove a spec and its associated frame counter."""
        if data_key not in self._specs.keys():
            # nothing to do if the key is not present
            return
        del self._specs[data_key]
        del self._indeces[data_key]
        del self._signals[data_key]
        del self._setters[data_key]

    def replace(self, spec: StreamSpec) -> None:
        """Update a spec before opening a stream, keeping its current frame counter.

        Allows `prepare()` to run more than once per run, reusing
        the same data provider without losing the frame count.
        """
        if spec.data_key not in self._specs.keys():
            raise KeyError(f"Key '{spec.data_key!r}' is not routed.")
        self._specs[spec.data_key] = spec

    def mark_written(self, data_key: str) -> None:
        """Mark that a frame has been written for `data_key`."""
        self._indeces[data_key] += 1
        self._setters[data_key](self._indeces[data_key])


__all__ = [
    "FrameRouter",
]
