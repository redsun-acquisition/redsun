"""Tests for the experimental layer's logging helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from redsun.experimental.log import (
    DATE_FORMAT,
    ContextualAdapter,
    GlobalFormatter,
    Loggable,
    add_handler,
    logger,
    remove_handler,
    set_level,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


class Stage(Loggable):
    """A component that logs, named as every component is."""

    def __init__(self, name: str) -> None:
        self.name = name


class Anonymous(Loggable):
    """A component with no name, which the adapter must still handle."""


@pytest.fixture
def captured() -> Iterator[logging.Handler]:
    """Attach a recording handler, and leave the shared logger as it was."""
    handler = logging.Handler()
    handler.records = []  # type: ignore[attr-defined]
    handler.emit = handler.records.append  # type: ignore[attr-defined, method-assign]
    level, handlers = logger.level, list(logger.handlers)
    add_handler(handler)
    yield handler
    logger.setLevel(level)
    logger.handlers = handlers


def _formatted(record: logging.LogRecord) -> str:
    """Return *record* as the shared formatter writes it."""
    return GlobalFormatter(datefmt=DATE_FORMAT).format(record)


def test_a_handler_without_a_formatter_is_given_the_shared_one(
    captured: logging.Handler,
) -> None:
    """A record reads the same wherever it lands, so the default is filled in."""
    assert isinstance(captured.formatter, GlobalFormatter)


def test_a_handler_keeps_a_formatter_it_arrived_with() -> None:
    own = logging.Formatter("%(message)s")
    handler = logging.Handler()
    handler.setFormatter(own)

    add_handler(handler)
    try:
        assert handler.formatter is own
    finally:
        remove_handler(handler)


def test_removing_a_handler_stops_the_records(captured: logging.Handler) -> None:
    logger.info("before")

    remove_handler(captured)
    logger.info("after")

    assert [record.getMessage() for record in captured.records] == ["before"]  # type: ignore[attr-defined]


def test_removing_a_handler_that_was_never_added_is_not_an_error() -> None:
    """Teardown runs on paths that may not have installed one."""
    remove_handler(logging.Handler())


def test_the_level_is_matched_without_regard_to_case(
    captured: logging.Handler,
) -> None:
    set_level("debug")
    logger.debug("visible")

    set_level(logging.WARNING)
    logger.debug("hidden")

    assert [record.getMessage() for record in captured.records] == ["visible"]  # type: ignore[attr-defined]


def test_a_level_naming_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="NONSENSE"):
        set_level("nonsense")


def test_a_component_logs_under_its_class_and_its_name(
    captured: logging.Handler,
) -> None:
    """The context is what tells two components of one class apart."""
    set_level(logging.INFO)

    Stage("stage_x").logger.info("moved")

    line = _formatted(captured.records[0])  # type: ignore[attr-defined]
    assert "[Stage -> stage_x]: moved" in line


def test_a_component_with_no_name_still_logs(captured: logging.Handler) -> None:
    set_level(logging.INFO)

    Anonymous().logger.info("ready")

    line = _formatted(captured.records[0])  # type: ignore[attr-defined]
    assert "[Anonymous]: ready" in line
    assert "->" not in line


def test_a_record_below_info_carries_where_it_came_from(
    captured: logging.Handler,
) -> None:
    """A warning is something to chase, so it names the file and the line."""
    set_level(logging.DEBUG)

    Stage("stage_x").logger.warning("slow")

    assert _formatted(captured.records[0]).endswith(")")  # type: ignore[attr-defined]
    assert "test_experimental_log.py:" in _formatted(captured.records[0])  # type: ignore[attr-defined]


def test_an_info_record_carries_no_file_or_line(captured: logging.Handler) -> None:
    set_level(logging.INFO)

    Stage("stage_x").logger.info("moved")

    assert "test_experimental_log.py:" not in _formatted(captured.records[0])  # type: ignore[attr-defined]


def test_the_adapter_keeps_extras_a_caller_passed(captured: logging.Handler) -> None:
    """The context is added to what the caller sent, not in place of it."""
    adapter = ContextualAdapter(logger, Stage("stage_x"))

    _, kwargs = adapter.process("moved", {"extra": {"axis": "x"}})

    assert kwargs["extra"] == {"axis": "x", "clsname": "Stage", "uid": "stage_x"}
