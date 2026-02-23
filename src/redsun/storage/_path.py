# SPDX-License-Identifier: Apache-2.0
# The design of this module is heavily inspired by ophyd-async
# (https://github.com/bluesky/ophyd-async), developed by the Bluesky collaboration.
# ophyd-async is licensed under the BSD 3-Clause License.
# No source code from ophyd-async has been copied; the PathProvider / FilenameProvider
# composable pattern was studied and independently re-implemented for redsun,
# with URI-based paths for storage location flexibility.

"""Path and filename providers for storage backends."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from urllib.parse import urlparse
from urllib.request import url2pathname

if TYPE_CHECKING:
    from pathlib import Path
    from typing import ClassVar


def from_uri(uri: str) -> str:
    """Convert a URI to a filesystem path if local, otherwise return as-is."""
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return url2pathname(parsed.path)
    return uri


@dataclass
class PathInfo:
    """Where and how a storage backend should write data for one device.

    !!! note

        For local file storage, The `store_uri` must be converted to
        a concrete filesystem path before use. This is responsibility
        of the backend writer.

        An helper method [`from_uri`][redsun.storage._path.from_uri]
        is provided for this purpose.

    Attributes
    ----------
    store_uri : str
        URI of the store root.  For local Zarr this is a ``file://`` URI.
        Example: ``"file:///data/scan001.zarr"``.
    array_key : str
        Key (array name) within the store for this device's data.
        Defaults to the device name.
    capacity : int
        Maximum number of frames to accept.  `0` means unlimited.
    mimetype_hint : str
        MIME type hint for the backend.  Consumers may use this to select
        the correct reader.
    extra : dict[str, Any]
        Optional backend-specific metadata (e.g. OME-Zarr axis labels,
        physical units).  Base writers ignore this field.
    """

    store_uri: str
    array_key: str
    capacity: int = 0
    mimetype_hint: str = "application/x-zarr"
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class FilenameProvider(Protocol):
    """Callable that produces a filename (without extension) for a device."""

    def __call__(self, device_name: str | None = None) -> str:
        """Return a filename for the given device.

        Parameters
        ----------
        device_name : str | None
            Name of the device requesting a filename.  Implementations may
            ignore this if the filename is device-agnostic.

        Returns
        -------
        str
            A filename string without extension.
        """
        ...


@runtime_checkable
class PathProvider(Protocol):
    """Callable that produces [`PathInfo`][redsun.storage.PathInfo] for a device."""

    def __call__(self, device_name: str | None = None) -> PathInfo:
        """Return path information for the given device.

        Parameters
        ----------
        device_name : str | None
            Name of the device requesting path information.

        Returns
        -------
        PathInfo
            Complete path and storage metadata for the device.
        """
        ...


class DateTimeMixin:
    """Mixin providing class variable for current date string (YYYY_MM_DD) to be used in filename generation."""

    _current_date: ClassVar[str] = datetime.datetime.now().strftime("%Y_%m_%d")


class AutoIncrementFilenameProvider(FilenameProvider, DateTimeMixin):
    """Returns a numerically incrementing filename on each call.

    Parameters
    ----------
    base : str
        Optional base prefix for the filename.
    base_dir : Path | None
        Optional directory to scan for
        existing files matching the pattern `{base}_{counter}`
        to initialize the counter.
        If `None` (default), the counter starts at `start` without scanning.
    max_digits : int
        Zero-padding width for the counter.
    start : int
        Initial counter value.
    step : int
        Increment per call.
    delimiter : str
        Separator between *base* and counter.
    """

    def __init__(
        self,
        base: str = "",
        base_dir: Path | None = None,
        max_digits: int = 5,
        start: int = 0,
        step: int = 1,
        delimiter: str = "_",
        suffix: str = "",
    ) -> None:
        self._base = base
        self._max_digits = max_digits
        self._step = step
        self._delimiter = delimiter
        self._current = self._scan(base_dir, suffix) if base_dir else start

    def _scan(self, base_dir: Path, suffix: str) -> int:
        """Scan *base_dir* for existing files matching the pattern and return max + 1."""
        pattern = (
            f"*_{self._base}{self._delimiter}*{suffix}"
            if self._base
            else f"*{self._delimiter}*{suffix}"
        )
        counters = []
        for p in base_dir.glob(pattern):
            try:
                counters.append(int(p.stem.split(self._delimiter)[-1]))
            except ValueError:
                continue
        return max(counters) + 1 if counters else 0

    def __call__(self, device_name: str | None = None) -> str:
        """Return the next incremented filename."""
        if len(str(self._current)) > self._max_digits:
            raise ValueError(f"Counter exceeded maximum of {self._max_digits} digits")
        padded = f"{self._current:0{self._max_digits}}"
        name = f"{self._base}{self._delimiter}{padded}" if self._base else padded
        name = "_".join([self._current_date, name])
        self._current += self._step
        return name


class StaticPathProvider(PathProvider):
    """Provides [`PathInfo`][redsun.storage.PathInfo] rooted at a fixed base URI.

    Composes a [`FilenameProvider`][redsun.storage.FilenameProvider]
    (for the array key / filename) with a fixed `base_uri` (for the store location).

    Parameters
    ----------
    filename_provider : FilenameProvider
        Callable that returns a filename for each device.
    base_uri : str
        Base URI for the store root (e.g. `"file:///data"`).
    mimetype_hint : str
        MIME type hint forwarded to [`PathInfo`][redsun.storage.PathInfo].
    capacity : int
        Default frame capacity forwarded to [`PathInfo`][redsun.storage.PathInfo].
    """

    def __init__(
        self,
        filename_provider: FilenameProvider,
        base_uri: str,
        mimetype_hint: str = "application/x-zarr",
        capacity: int = 0,
    ) -> None:
        self._filename_provider = filename_provider
        self._base_uri = base_uri.rstrip("/")
        self._mimetype_hint = mimetype_hint
        self._capacity = capacity

    def __call__(self, device_name: str | None = None) -> PathInfo:
        """Return [`PathInfo`][redsun.storage.PathInfo] for *device_name*."""
        filename = self._filename_provider(device_name)
        store_uri = f"{self._base_uri}/{filename}"
        array_key = device_name or filename
        return PathInfo(
            store_uri=store_uri,
            array_key=array_key,
            capacity=self._capacity,
            mimetype_hint=self._mimetype_hint,
        )
