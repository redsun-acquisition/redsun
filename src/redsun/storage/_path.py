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

    def __call__(self, key: str | None = None, group: str | None = None) -> str:
        """Return a filename stem for *key* and *group*.

        Parameters
        ----------
        key : str | None
            Discriminator passed by the caller — typically a plan name
            (when called from a presenter) or a device name (when called
            from a writer).  Implementations may ignore it if the filename
            is key-agnostic.
        group : str | None
            Writer group name (e.g. ``'default'``).  When provided,
            implementations should embed it in the filename so that
            outputs from different writer groups do not collide.

        Returns
        -------
        str
            A filename stem without extension.
        """
        ...


@runtime_checkable
class PathProvider(Protocol):
    """Callable that produces [`PathInfo`][redsun.storage.PathInfo] for a given key."""

    def __call__(self, key: str | None = None, group: str | None = None) -> PathInfo:
        """Return path information for *key* and *group*.

        Parameters
        ----------
        key : str | None
            Discriminator passed by the caller — typically a plan name
            (when called from a presenter) or a device name (when called
            from a writer).
        group : str | None
            Writer group name (e.g. ``'default'``).  When provided,
            the path should reflect the group so that outputs from
            different writer groups do not collide.

        Returns
        -------
        [`PathInfo`][redsun.storage.PathInfo]
            Complete path and storage metadata.
        """
        ...


class SessionPathProvider(PathProvider):
    """Provides structured, session-scoped paths with per-key auto-increment counters.

    Produces URIs of the form::

        file:///<base_dir>/<session>/<YYYY_MM_DD>/<key>_<counter>

    where ``<key>`` is the value passed to [`__call__`][redsun.storage.SessionPathProvider.__call__] (e.g. the plan
    name), and ``<counter>`` is a zero-padded integer that increments
    independently for each distinct ``key``.  Calling with ``key=None``
    uses ``"default"`` as the key.

    The date segment is fixed at construction time so that a session
    started just before midnight does not split its files across two
    date directories.

    Parameters
    ----------
    base_dir :
        Root directory for all output files.
        Defaults to ``~/redsun-storage``.
    session : str
        Session name, used as the second path segment.
        Defaults to ``"default"``.
    max_digits : int
        Zero-padding width for the counter.  Defaults to ``5``.
    mimetype_hint : str
        MIME type hint forwarded to [`PathInfo`][redsun.storage.PathInfo].
    capacity : int
        Default frame capacity forwarded to [`PathInfo`][redsun.storage.PathInfo].

    Examples
    --------
    ```python
        provider = SessionPathProvider(base_dir=Path("/data"), session="exp1")
        info = provider("live_stream")
        info.store_uri                              # 'file:///data/exp1/2026_02_24/live_stream_00000'
        provider("live_stream").store_uri           # 'file:///data/exp1/2026_02_24/live_stream_00001'
        provider("snap").store_uri                  # 'file:///data/exp1/2026_02_24/snap_00000'
        provider("live_stream", group="cam").store_uri  # 'file:///data/exp1/2026_02_24/live_stream_cam_00000'
    ```
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        session: str = "default",
        max_digits: int = 5,
        mimetype_hint: str = "application/x-zarr",
        capacity: int = 0,
    ) -> None:
        self._base_dir = (
            base_dir if base_dir is not None else Path.home() / "redsun-storage"
        )
        self._session = session
        self._max_digits = max_digits
        self._mimetype_hint = mimetype_hint
        self._capacity = capacity
        self._date = datetime.datetime.now().strftime("%Y_%m_%d")
        self._counters: dict[str, int] = self._scan_existing()
        self._time_resolved_path = self._base_dir / self._session / self._date
        self._time_resolved_path.mkdir(parents=True, exist_ok=True)

    @property
    def session(self) -> str:
        """The active session name."""
        return self._session

    @session.setter
    def session(self, value: str) -> None:
        """Update the session name and rescan the new session directory.

        Counters are rebuilt from whatever already exists under
        ``<base_dir>/<value>/<date>/`` so that numbering continues
        correctly if the session was used in a previous run.
        """
        self._session = value
        self._time_resolved_path = self._base_dir / self._session / self._date
        self._time_resolved_path.mkdir(parents=True, exist_ok=True)
        self._counters = self._scan_existing()

    @property
    def base_dir(self) -> Path:
        """The root output directory."""
        return self._base_dir

    @base_dir.setter
    def base_dir(self, value: Path) -> None:
        """Update the root output directory and rescan.

        Counters are rebuilt from whatever already exists under
        ``<value>/<session>/<date>/`` so that numbering continues
        correctly if the directory was used in a previous run.
        """
        self._base_dir = value
        self._counters = self._scan_existing()

    def _scan_existing(self) -> dict[str, int]:
        """Scan the current date directory and return counters initialised from existing directories.

        Looks for directories directly inside
        ``<base_dir>/<session>/<date>/`` whose names match
        ``<key>_<N>`` (last ``_``-delimited segment is a pure integer).
        For each key, the counter is set to ``max(N) + 1`` so the next
        call produces a name that does not collide with existing data.

        Entries whose names cannot be parsed are silently ignored.
        If the directory does not exist yet, an empty dict is returned.

        Returns
        -------
        dict[str, int]
            Mapping of key to next counter value.
        """
        directory = self._base_dir / self._session / self._date
        counters: dict[str, int] = {}
        if not directory.is_dir():
            return counters
        for entry in directory.iterdir():
            if not entry.is_dir():
                continue
            name = entry.name
            parts = name.rsplit("_", 1)
            if len(parts) != 2:
                continue
            key, suffix = parts
            if not suffix.isdigit():
                continue
            n = int(suffix)
            if n + 1 > counters.get(key, 0):
                counters[key] = n + 1
        return counters

    def __call__(self, key: str | None = None, group: str | None = None) -> PathInfo:
        """Return a fresh [`PathInfo`][redsun.storage.PathInfo] for *key* and advance its counter.

        Parameters
        ----------
        key : str | None
            Discriminator for the counter bucket — typically a plan name
            (e.g. ``"live_stream"``, ``"snap"``).
            ``None`` maps to ``"default"``.
        group : str | None
            Writer group name (e.g. ``"default"``).  When provided the
            filename becomes ``<key>_<group>_<counter>`` and the counter
            is tracked independently per ``(key, group)`` pair so that
            different writer groups never collide.

        Returns
        -------
        [`PathInfo`][redsun.storage.PathInfo]
            Path rooted at
            ``<base_dir>/<session>/<YYYY_MM_DD>/<key>[_<group>]_<counter>``.
        """
        resolved_key = key or "default"
        bucket = f"{resolved_key}_{group}" if group else resolved_key
        current = self._counters.get(bucket, 0)

        if len(str(current)) > self._max_digits:
            raise ValueError(
                f"Counter for key {bucket!r} exceeded "
                f"maximum of {self._max_digits} digits"
            )

        padded = f"{current:0{self._max_digits}}"
        stem = (
            f"{resolved_key}_{group}_{padded}" if group else f"{resolved_key}_{padded}"
        )
        directory = self._base_dir / self._session / self._date
        store_uri = f"file://{directory.as_posix()}/{stem}"

        self._counters[bucket] = current + 1

        return PathInfo(
            store_uri=store_uri,
            array_key=resolved_key,
            capacity=self._capacity,
            mimetype_hint=self._mimetype_hint,
        )
