"""Tests for describing the keys a plugin's components take."""

from __future__ import annotations

from importlib.metadata import EntryPoint
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
from jsonschema import Draft202012Validator

from redsun import Session
from redsun._describe import describe_report
from redsun.catalog import CatalogAddress
from redsun.compute._pool import PoolExecutor
from redsun.injection import Registry
from redsun.injection._registry import SESSION
from redsun.session._base import HELD

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

    from redsun._reports import DescribeReport


@pytest.fixture
def a_plugin_naming_a_missing_class(tmp_path: Path) -> Generator[None, None, None]:
    """Present a plugin whose manifest lists a presenter class that does not exist."""
    (tmp_path / "redsun.yaml").write_text(
        "presenters:\n  gone: mock_bundle.described:Gone\n"
    )
    entry = mock.Mock(spec=EntryPoint)
    entry.name = "gone-bundle"
    entry.value = "redsun.yaml"
    entry.dist = None
    with (
        mock.patch("redsun._manifest.entry_points", return_value=[entry]),
        mock.patch("redsun._manifest.files", side_effect=lambda _: tmp_path),
    ):
        yield


def schema_of(report: DescribeReport, plugin_id: str) -> dict[str, Any]:
    """Return the schema the report gives the component *plugin_id*."""
    [component] = [c for c in report.components if c.plugin_id == plugin_id]
    assert component.json_schema is not None
    return component.json_schema


def test_held_names_every_type_the_session_holds_itself() -> None:
    """Fail when the session registers a type under its own name that `HELD` misses."""
    seen: set[object] = set()

    class Recording(Registry):
        def register(
            self, key: object, factory: Callable[[], object], *, owner: str
        ) -> None:
            if owner == SESSION:
                seen.add(key)
            super().register(key, factory, owner=owner)

    class Empty(Session):
        def make_registry(self) -> Registry:
            return Recording()

    session = Empty({"session": "held"})
    session.build()
    session.shutdown()

    executors = {
        key for key in seen if isinstance(key, type) and issubclass(key, PoolExecutor)
    }
    assert seen - executors <= set(HELD)
    assert set(HELD) - seen <= {CatalogAddress}


def test_a_plugin_is_described_entry_by_entry(mock_plugin: None) -> None:
    """Describe each component of the mock bundle, with schema, session list and problems."""
    report = describe_report("mock-bundle")

    by_id = {c.plugin_id: c for c in report.components}
    described = by_id["described"]
    assert described.status == "failed"
    assert described.reason is not None and "Unavailable" in described.reason
    schema = described.json_schema
    assert schema is not None
    step = schema["properties"]["step"]
    assert step["title"] == "Step" and step["unit"] == "um"
    assert step["exclusiveMinimum"] == 0 and step["default"] == 1.0
    assert schema["properties"]["mode"]["enum"] == ["fast", "fine"]
    assert "default" not in schema["properties"]["marker"]
    assert schema["properties"]["plugin_id"] == {"const": "described"}
    assert sorted(schema["required"]) == ["plugin_id", "plugin_name"]
    assert {(p.name, p.file) for p in described.session} == {
        ("calibration", True),
        ("devices", False),
    }
    assert {
        (p.kind, p.where) for p in report.problems if p.where.startswith("described.")
    } == {("parameter", "described.scale"), ("parameter", "described.missing")}
    failed = {c.plugin_id for c in report.components if c.status == "failed"}
    assert failed == {"described", "mapped"}


@pytest.mark.parametrize(
    ("entry", "valid"),
    [
        ({"prefix": "X:"}, True),
        ({"service": "ioc"}, True),
        ({"services": {"prefix": "ioc"}}, True),
        ({}, False),
    ],
    ids=["prefix", "service", "services", "neither"],
)
def test_a_device_keyword_may_come_from_a_service(
    mock_plugin: None, entry: dict[str, object], valid: bool
) -> None:
    """Accept the prefix itself or a service giving it, and refuse an entry with neither."""
    schema = schema_of(describe_report("mock-bundle", "prefixed"), "prefixed")

    full = {"plugin_name": "mock-bundle", "plugin_id": "prefixed", **entry}
    assert Draft202012Validator(schema).is_valid(full) is valid


@pytest.mark.parametrize(
    ("entry", "valid"),
    [({}, False), ({"calibration": {"offset": 1.0}}, True)],
    ids=["missing", "given"],
)
def test_a_device_takes_a_model_type_key_from_the_file(
    mock_plugin: None, entry: dict[str, object], valid: bool
) -> None:
    """Require a device's model-type key in the file, since the session fills nothing of a device."""
    report = describe_report("mock-bundle", "calibrated")
    [component] = report.components

    full = {
        "plugin_name": "mock-bundle",
        "plugin_id": "calibrated",
        "prefix": "X:",
        **entry,
    }
    assert Draft202012Validator(schema_of(report, "calibrated")).is_valid(full) is valid
    assert component.session == []


@pytest.mark.parametrize(("step", "valid"), [(0, False), (2, True)])
def test_a_limit_is_enforced_by_the_schema(
    mock_plugin: None, step: float, valid: bool
) -> None:
    """Refuse a value the constructor's limit excludes, and accept one it allows."""
    schema = schema_of(describe_report("mock-bundle", "described"), "described")

    full = {"plugin_name": "mock-bundle", "plugin_id": "described", "step": step}
    assert Draft202012Validator(schema).is_valid(full) is valid


@pytest.mark.parametrize(
    ("plugin_name", "plugin_id", "where"),
    [
        ("nope", None, "nope"),
        ("mock-bundle", "nope", "mock-bundle.nope"),
        ("mock-bundle", "mock-services", "mock-bundle.mock-services"),
    ],
    ids=["plugin", "id", "provider"],
)
def test_an_unknown_plugin_or_id_is_a_manifest_problem(
    mock_plugin: None, plugin_name: str, plugin_id: str | None, where: str
) -> None:
    """Report a plugin, an id or a group describing does not cover, with no components."""
    report = describe_report(plugin_name, plugin_id)

    assert [(p.kind, p.where) for p in report.problems] == [("manifest", where)]
    assert report.components == []


def test_a_class_that_cannot_be_imported_fails(
    a_plugin_naming_a_missing_class: None,
) -> None:
    """Fail a component whose class does not import, with no schema."""
    [gone] = describe_report("gone-bundle").components

    assert gone.status == "failed"
    assert gone.json_schema is None
    assert gone.reason is not None and "Gone" in gone.reason
