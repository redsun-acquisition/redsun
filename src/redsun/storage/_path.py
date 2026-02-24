# SPDX-License-Identifier: Apache-2.0
# The file and path providers are inspired by ophyd-async
# (https://github.com/bluesky/ophyd-async), developed by the Bluesky collaboration.
# ophyd-async is licensed under the BSD 3-Clause License.

"""Path and filename providers for storage backends."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass
class PathInfo:
    """Where and how a storage backend should write data for one device.

    !!! note

        For local file storage, the `store_uri` must be converted to
        a concrete filesystem path before use. This is the responsibility
        of the backend writer.

    Attributes
    ----------
    store_uri : str
        URI of the store root.  For local Zarr this is a ``file://`` URI.
        Example: ``"file:///data/2026_02_24/live_stream_00000.zarr"``.
    array_key : str
        Key (array name) within the store for this device's data.
        Defaults to the key passed to the provider (usually the device name).
    capacity : int
        Maximum number of frames to accept.  ``0`` means unlimited.
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
    """Callable that produces a filename stem for a given key."""

    def __call__(self, key: str | None = None) -> str:
        """Return a filename stem for *key*.

        Parameters
        ----------
        key : str | None
            Discriminator passed by the caller — typically a device name
            (when called from a writer) or a plan name (when called from a
            presenter).  Implementations may ignore it if the filename is
            key-agnostic.

        Returns
        -------
        str
            A filename stem without extension.
        """
        ...


@runtime_checkable
class PathProvider(Protocol):
    """Callable that produces :class:`PathInfo` for a given key."""

    def __call__(self, key: str | None = None) -> PathInfo:
        """Return path information for *key*.

        Parameters
        ----------
        key : str | None
            Discriminator passed by the caller — typically a device name
            (when called from a writer) or a plan name (when called from a
            presenter).

        Returns
        -------
        PathInfo
            Complete path and storage metadata.
        """
        ...


class SessionPathProvider(PathProvider):
    """Provides structured, session-scoped paths with per-key auto-increment counters.

    Produces URIs of the form::

        file:///<base_dir>/<session>/<YYYY_MM_DD>/<key>_<counter>

    where ``<key>`` is the value passed to :meth:`__call__` (e.g. the plan
    name), and ``<counter>`` is a zero-padded integer that increments
    independently for each distinct ``key``.  Calling with ``key=None``
    uses ``"default"`` as the key.

    The date segment is fixed at construction time so that a session
    started just before midnight does not split its files across two
    date directories.

    ```python
        provider = SessionPathProvider(base_dir=Path("/data"), session="exp1")
        info = provider("live_stream")
        info.store_uri                      # output: file:///data/exp1/2026_02_24/live_stream_00000
        provider("live_stream").store_uri   # output: file:///data/exp1/2026_02_24/live_stream_00001
        provider("snap").store_uri          # output: file:///data/exp1/2026_02_24/snap_00000
    ```

    Parameters
    ----------
    base_dir :
        Root directory for all output files.
        Defaults to ``~/redsun-storage``.
    session : str
        Session name, used as the second path segment.
        Defaults to ``"redsun-application"``.
    max_digits : int
        Zero-padding width for the counter. Defaults to ``5``.
    mimetype_hint : Storage
        MIME type hint forwarded to [`PathInfo`][redsun.storage.PathInfo].
    capacity : int
        Default frame capacity forwarded to [`PathInfo`][redsun.storage.PathInfo].

    Attributes
    ----------
    session: str
        Session name, used as the second path segment.
    base_dir: Path
        Root directory for all output files.
        Can be updated after construction; updating it resets all counters to zero.
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        session: str = "redsun-application",
        max_digits: int = 5,
        mimetype_hint: str = "application/x-zarr",
        capacity: int = 0,
    ) -> None:
        self._base_dir = (
            base_dir if base_dir is not None else Path.home() / "redsun-storage"
        )
        self.session = session
        self._max_digits = max_digits
        self._mimetype_hint = mimetype_hint
        self._capacity = capacity
        self._date = datetime.datetime.now().strftime("%Y_%m_%d")
        self._counters: dict[str, int] = {}

    @property
    def base_dir(self) -> Path:
        """The root output directory."""
        return self._base_dir

    @base_dir.setter
    def base_dir(self, value: Path) -> None:
        """Update the root output directory and reset all counters.

        Resetting counters ensures numbering restarts from zero when the
        user chooses a new output location.
        """
        self._base_dir = value
        self._counters.clear()

    def __call__(self, key: str | None = None) -> PathInfo:
        """Return a fresh :class:`PathInfo` for *key* and advance its counter.

        Parameters
        ----------
        key :
            Discriminator for the counter bucket — typically a plan name
            (e.g. ``"live_stream"``, ``"snap"``) when called from a
            presenter, or a device name when called from a writer.
            ``None`` maps to ``"default"``.

        Returns
        -------
        PathInfo
            Path rooted at
            ``<base_dir>/<session>/<YYYY_MM_DD>/<key>_<counter>``.
        """
        resolved_key = key or "default"
        current = self._counters.get(resolved_key, 0)

        if len(str(current)) > self._max_digits:
            raise ValueError(
                f"Counter for key {resolved_key!r} exceeded "
                f"maximum of {self._max_digits} digits"
            )

        padded = f"{current:0{self._max_digits}}"
        filename = f"{resolved_key}_{padded}"
        directory = self._base_dir / self.session / self._date
        store_uri = f"file://{directory}/{filename}"

        self._counters[resolved_key] = current + 1

        return PathInfo(
            store_uri=store_uri,
            array_key=resolved_key,
            capacity=self._capacity,
            mimetype_hint=self._mimetype_hint,
        )
