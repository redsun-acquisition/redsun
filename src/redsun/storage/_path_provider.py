# redsun/storage/_path.py
"""Session-scoped path provider with runtime, presenter-controllable naming."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import TYPE_CHECKING

from ophyd_async.core import PathInfo, PathProvider, soft_signal_r_and_setter

if TYPE_CHECKING:
    from ophyd_async.core import SignalR

#: Tokens available to a filename ``template``.
_TEMPLATE_TOKENS = ("plan", "counter", "session", "date", "datakey")

DEFAULT_TEMPLATE = "{plan}_{counter}"


@dataclass(frozen=True, slots=True)
class PathSignals:
    """Read-only signals for the view to observe, keyed by knob name."""

    base_dir: SignalR[str]
    session: SignalR[str]
    name: SignalR[str]
    template: SignalR[str]
    override: SignalR[str]


class SessionPathProvider(PathProvider):
    """Session-scoped path provider with runtime, presenter-controllable naming.

    The output path is composed from four independently settable knobs. Each is
    exposed as a **read-only** ophyd-async signal for the view to observe, and
    mutated through a **synchronous** setter that the presenter calls:

    * ``base_dir`` — root output directory (``set_base_dir``).
    * ``session`` — session segment (``set_session``).
    * ``plan`` — per-run plan segment, set by a presenter each run.
    * ``name`` — explicit filename stem; empty means *use the template*
      (``set_name``).

    Parameters
    ----------
    base_dir : Path | None
        Root directory. Defaults to ``~/redsun-storage``.
    session : str
        Session segment. Defaults to ``"default"``.
    max_digits : int
        Zero-padding width for the auto-increment counter. Defaults to ``5``.
    template : str
        Initial stem template. Defaults to ``"{plan}_{counter}"``.
    name_is_exact : bool
        When an explicit ``name`` is set and this is ``False`` (default), the
        counter is still appended so unattended acquisition can never silently
        overwrite. When ``True``, the name is honoured verbatim.
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        session: str = "default",
        max_digits: int = 5,
        template: str = DEFAULT_TEMPLATE,
        name_is_exact: bool = False,
    ) -> None:
        self._base_dir = (
            base_dir if base_dir is not None else Path.home() / "redsun-storage"
        )
        self.plan: str | None = None
        self._session = session
        self._max_digits = max_digits
        self._date = datetime.datetime.now().strftime("%Y_%m_%d")
        self._name_is_exact = name_is_exact

        # Plain attributes are the source of truth for hot-path reads in
        # __call__; the paired setters push the same value onto the read-only
        # signal for observers. Both are updated together, synchronously, in
        # the set_* methods — so there is no signal-callback wiring and no
        # run_coro anywhere in this class.
        self._name = ""
        self._template = template
        self._override = ""
        self._override_sticky = False

        base_dir_sig, self._set_base_dir_sig = soft_signal_r_and_setter(
            str, initial_value=str(self._base_dir)
        )
        session_sig, self._set_session_sig = soft_signal_r_and_setter(
            str, initial_value=self._session
        )
        name_sig, self._set_name_sig = soft_signal_r_and_setter(str, initial_value="")
        template_sig, self._set_template_sig = soft_signal_r_and_setter(
            str, initial_value=template
        )
        override_sig, self._set_override_sig = soft_signal_r_and_setter(
            str, initial_value=""
        )

        self._counters: dict[str, int] = self._scan_existing()

        self._path_signals = PathSignals(
            base_dir=base_dir_sig,
            session=session_sig,
            name=name_sig,
            template=template_sig,
            override=override_sig,
        )

    @property
    def signals(self) -> PathSignals:
        """Read-only signals keyed by knob name, for the view to observe."""
        return self._path_signals

    def set_base_dir(self, value: str | Path) -> None:
        """Set the root output directory, rescanning counters on change."""
        new = Path(value)
        if new != self._base_dir:
            self._base_dir = new
            self._set_base_dir_sig(str(new))
            self._counters = self._scan_existing()

    def set_session(self, value: str) -> None:
        """Set the session segment, rescanning counters on change."""
        if value != self._session:
            self._session = value
            self._set_session_sig(value)
            self._counters = self._scan_existing()

    def set_name(self, name: str, *, exact: bool | None = None) -> None:
        """Set the explicit filename stem for upcoming runs.

        Empty string restores template-based naming. ``exact`` overrides the
        per-instance ``name_is_exact`` policy when given.
        """
        if exact is not None:
            self._name_is_exact = exact
        self._name = name
        self._set_name_sig(name)

    def set_template(self, template: str) -> None:
        """Set the stem composition template (used when no explicit name).

        Validated eagerly so a malformed template is rejected here rather than
        at resolution time.
        """
        self._validate_template(template)
        self._template = template
        self._set_template_sig(template)

    def set_destination(self, path: str | PurePath, *, sticky: bool = False) -> None:
        """Pin a fully-resolved destination, bypassing generation.

        ``sticky=False`` (default) is consumed by the next resolution, then
        normal generation resumes. ``sticky=True`` persists until cleared — a
        GUI fixing an output file.
        """
        self._override_sticky = sticky
        self._override = str(path)
        self._set_override_sig(self._override)

    def clear_destination(self) -> None:
        """Drop any pinned destination and resume generated paths."""
        self._override_sticky = False
        self._override = ""
        self._set_override_sig("")

    def _scan_existing(self) -> dict[str, int]:
        """Initialise per-plan counters from existing directory contents."""
        directory = self._base_dir / self._session
        counters: dict[str, int] = {}
        if not directory.is_dir():
            return counters
        for plan_dir in directory.iterdir():
            if not plan_dir.is_dir():
                continue
            for date_dir in plan_dir.iterdir():
                if not date_dir.is_dir():
                    continue
                for entry in date_dir.iterdir():
                    parts = entry.stem.rsplit("_", 1)
                    if len(parts) != 2 or not parts[1].isdigit():
                        continue
                    key, suffix = parts
                    n = int(suffix)
                    if n + 1 > counters.get(key, 0):
                        counters[key] = n + 1
        return counters

    @staticmethod
    def _validate_template(template: str) -> None:
        try:
            template.format(plan="", counter="", session="", date="", datakey="")
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(
                f"Invalid filename template {template!r}; "
                f"available tokens: {_TEMPLATE_TOKENS}"
            ) from exc

    def _compose_stem(self, padded: str, plan_segment: str, datakey: str | None) -> str:
        if self._name:
            return self._name if self._name_is_exact else f"{self._name}_{padded}"
        return self._template.format(
            plan=plan_segment,
            counter=padded,
            session=self._session,
            date=self._date,
            datakey=datakey or "default",
        )

    def __call__(self, datakey_name: str | None = None) -> PathInfo:
        """Return the output ``PathInfo`` for the next resolution.

        Resolution order: a pinned ``override`` (consumed unless sticky) wins
        outright; otherwise the stem comes from an explicit ``name`` or the
        ``template``, under ``<base_dir>/<session>/<plan>/<date>/``.
        """
        # 1. explicit full-path override (consume-once unless sticky).
        if self._override:
            p = PurePath(self._override)
            if not self._override_sticky:
                self._override = ""
                self._set_override_sig("")
            directory = Path(p.parent)
            directory.mkdir(parents=True, exist_ok=True)
            return PathInfo(directory_path=directory, filename=p.stem)

        # 2. generated path.
        plan_segment = self.plan if self.plan is not None else "default"
        bucket = plan_segment
        current = self._counters.get(bucket, 0)
        if len(str(current)) > self._max_digits:
            raise ValueError(
                f"Counter for key {bucket!r} exceeded "
                f"maximum of {self._max_digits} digits."
            )
        padded = f"{current:0{self._max_digits}}"
        stem = self._compose_stem(padded, plan_segment, datakey_name)
        directory = self._base_dir / self._session / plan_segment / self._date
        directory.mkdir(parents=True, exist_ok=True)
        self._counters[bucket] = current + 1
        return PathInfo(directory_path=directory, filename=stem)


_default_provider: SessionPathProvider | None = None


def get_path_provider(
    base_dir: Path | None = None,
    session: str = "default",
    max_digits: int = 5,
    template: str = DEFAULT_TEMPLATE,
    name_is_exact: bool = False,
) -> SessionPathProvider:
    """Return a shared, reusable ``SessionPathProvider`` (singleton)."""
    global _default_provider
    if _default_provider is None:
        _default_provider = SessionPathProvider(
            base_dir=base_dir,
            session=session,
            max_digits=max_digits,
            template=template,
            name_is_exact=name_is_exact,
        )
    return _default_provider


__all__ = ["SessionPathProvider", "get_path_provider"]
