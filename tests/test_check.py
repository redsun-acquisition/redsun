"""Tests for checking a session file without building it."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import pytest

from redsun._check import check_report

if TYPE_CHECKING:
    from pathlib import Path

    from redsun._reports import CheckReport

BUNDLE = {"plugin_name": "mock-bundle"}
"""The plugin every entry below names, as `mock_plugin` installs it."""


def records(report: CheckReport) -> dict[str, str]:
    """Return each component's status by name."""
    return {component.name: component.status for component in report.components}


def lookups(report: CheckReport) -> dict[str, str]:
    """Return each lookup's status by name."""
    return {lookup.name: lookup.status for lookup in report.lookups}


def test_a_check_records_each_component_and_lookup(mock_plugin: None) -> None:
    """Record what each entry and each name of two merged sources would give."""
    base: dict[str, Any] = {
        "session": "s",
        "presenters": {
            "m": {**BUNDLE, "plugin_id": "mock-late"},
            "ghost": {"plugin_name": "nope", "plugin_id": "x"},
            "fast": {**BUNDLE, "plugin_id": "mock-motor", "speed": 3},
            "pooled": {**BUNDLE, "plugin_id": "mock-motor", "workers": 2},
        },
        "views": {"v": {**BUNDLE, "plugin_id": "mock-motor-view", "title": "Motor"}},
        "services": {"ioc": {"plugin_name": "nope", "plugin_id": "x"}},
        "wiring": {
            "m2.sig_moved": "v.refresh",
            "m2.sig_unknown": ["v.refresh", "v.clear"],
        },
        "pairs": [["m2", "v"], ["m2", "nobody"]],
    }
    overlay = {"presenters": {"m2": {**BUNDLE, "plugin_id": "mock-motor"}}}

    report = check_report([base, overlay])

    assert records(report) == {
        "m": "passed",
        "ghost": "failed",
        "fast": "failed",
        "pooled": "passed",
        "m2": "passed",
        "v": "passed",
        "ioc": "failed",
    }
    assert lookups(report) == {
        "m2.sig_moved -> v.refresh": "passed",
        "m2.sig_unknown -> v.refresh": "undecided",
        "m2.sig_unknown -> v.clear": "undecided",
        "m2 <-> v": "passed",
        "m2 <-> nobody": "failed",
    }
    [fast] = [c for c in report.components if c.name == "fast"]
    assert fast.reason is not None and "speed" in fast.reason
    assert report.problems == []


@pytest.mark.parametrize(
    ("config", "kind"),
    [
        ({"devices": {}}, "session"),
        ({"session": "s", "frontend": "nowhere"}, "session"),
        (
            {
                "session": "s",
                "presenters": {"p": {**BUNDLE, "plugin_id": "mock-late", "workers": 0}},
            },
            "value",
        ),
        (
            {
                "session": "s",
                "presenters": {"motor_view": {**BUNDLE, "plugin_id": "mock-late"}},
                "stacks": {"motor": {**BUNDLE, "plugin_id": "mock-motor"}},
            },
            "session",
        ),
    ],
    ids=[
        "no session name",
        "unknown frontend",
        "bad value",
        "stack half named like a component",
    ],
)
def test_what_stops_a_check(
    mock_plugin: None, config: dict[str, Any], kind: str
) -> None:
    """Report one problem and no records for a file that cannot be read at all."""
    report = check_report([config])

    assert [problem.kind for problem in report.problems] == [kind]
    assert report.components == []
    assert report.lookups == []


def test_a_catalog_without_tiled_stops_a_check(
    mock_plugin: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Report a catalog the installed packages cannot serve as a session problem."""

    def missing() -> None:
        raise ImportError("install the catalog extra")

    monkeypatch.setattr("redsun.session._base.require_tiled", missing)

    report = check_report([{"session": "s", "storage": {"catalog": {}}}])

    [problem] = report.problems
    assert problem.kind == "session"
    assert "catalog extra" in problem.message


def test_a_file_for_a_frontend_not_installed_stops_a_check(
    mock_plugin: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Report a frontend whose packages are missing as a session problem, naming the extra."""
    monkeypatch.setitem(sys.modules, "redsun.qt", None)

    report = check_report([{"session": "s", "frontend": "qt"}])

    [problem] = report.problems
    assert problem.kind == "session"
    assert "'pyqt'" in problem.message


def test_a_skipped_manifest_is_a_problem_of_the_check(
    a_bad_plugin_beside_a_good_one: None,
) -> None:
    """Report a manifest discovery skipped, as `redsun plugins` does."""
    report = check_report([{"session": "s"}])

    assert [(p.kind, p.where) for p in report.problems] == [("manifest", "bad-bundle")]


def test_a_check_writes_nothing(mock_plugin: None, tmp_path: Path) -> None:
    """Leave the folders a session writes its logs, data and settings to untouched."""
    check_report(
        [{"session": "s", "presenters": {"m": {**BUNDLE, "plugin_id": "mock-late"}}}]
    )

    assert list(tmp_path.iterdir()) == []


def test_a_check_puts_the_log_level_back(mock_plugin: None) -> None:
    """Restore the `redsun` logger's level, also after a check that stopped."""
    logger = logging.getLogger("redsun")
    before = logger.level

    check_report([{"session": "s"}])
    check_report([{"devices": {}}])

    assert logger.level == before


@pytest.mark.qt
def test_a_check_of_a_qt_file_records_hooks_and_layout_names(mock_plugin: None) -> None:
    """Record a hook provider that fails and a layout name no view answers to."""
    report = check_report(
        [
            {
                "session": "s",
                "frontend": "qt",
                "views": {"v": {**BUNDLE, "plugin_id": "mock-motor-view"}},
                "hooks": {
                    "configure_application": {
                        "provider": "mock_bundle.hooks:MockStyle",
                        "kwargs": {"nonsense": 1},
                    }
                },
                "layout": {"regions": {"left": "ghost"}},
            }
        ]
    )

    [hook] = [c for c in report.components if c.group == "hooks"]
    assert hook.status == "failed"
    assert lookups(report)["ghost"] == "failed"
