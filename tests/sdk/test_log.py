from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from redsun.log import (
    DATE_FORMAT,
    GlobalFormatter,
    Loggable,
    add_handler,
    logger,
    remove_handler,
    set_level,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest import LogCaptureFixture


class MockLoggable(Loggable):
    @property
    def name(self) -> str:
        return "Test instance"


class LoggableNoName(Loggable):
    pass


class RecordingHandler(logging.Handler):
    """Keeps what it is given, so a test can see what reached it."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def restore_level() -> Iterator[None]:
    """Put the level back, so a test changing it does not reach the next one."""
    level = logger.level
    yield
    logger.setLevel(level)


def test_loggable(caplog: LogCaptureFixture) -> None:
    obj = MockLoggable()
    assert obj.name == "Test instance"

    with caplog.at_level(logging.DEBUG, logger="redsun"):
        obj.logger.info("Test info")
        obj.logger.debug("Test debug")
        obj.logger.warning("Test warning")
        obj.logger.error("Test error")
        obj.logger.critical("Test critical")
        obj.logger.exception("Test exception")

    assert len(caplog.handler.records) == 6
    assert "Test info" in caplog.handler.records[0].msg
    assert "Test debug" in caplog.handler.records[1].msg
    assert "Test warning" in caplog.handler.records[2].msg
    assert "Test error" in caplog.handler.records[3].msg
    assert "Test critical" in caplog.handler.records[4].msg
    assert "Test exception" in caplog.handler.records[5].msg

    for record in caplog.handler.records:
        # injected through 'extra', so not attributes of LogRecord itself
        assert "MockLoggable" in getattr(record, "clsname", "")
        assert "Test instance" in getattr(record, "uid", "")

    assert caplog.handler.records[0].levelname == "INFO"
    assert caplog.handler.records[1].levelname == "DEBUG"
    assert caplog.handler.records[2].levelname == "WARNING"
    assert caplog.handler.records[3].levelname == "ERROR"
    assert caplog.handler.records[4].levelname == "CRITICAL"
    assert caplog.handler.records[5].levelname == "ERROR"


def test_loggable_no_name(caplog: LogCaptureFixture) -> None:
    obj = LoggableNoName()

    with caplog.at_level(logging.DEBUG, logger="redsun"):
        obj.logger.info("Test info")
        obj.logger.debug("Test debug")
        obj.logger.warning("Test warning")
        obj.logger.error("Test error")
        obj.logger.critical("Test critical")
        obj.logger.exception("Test exception")

    assert len(caplog.handler.records) == 6
    assert "Test info" in caplog.handler.records[0].msg
    assert "Test debug" in caplog.handler.records[1].msg
    assert "Test warning" in caplog.handler.records[2].msg
    assert "Test error" in caplog.handler.records[3].msg
    assert "Test critical" in caplog.handler.records[4].msg
    assert "Test exception" in caplog.handler.records[5].msg

    for record in caplog.handler.records:
        assert "LoggableNoName" in getattr(record, "clsname", "")


class EmptyName(Loggable):
    name = ""


def _formatted(obj: Loggable, caplog: LogCaptureFixture) -> str:
    """Return what a handler would have written for one record from *obj*."""
    with caplog.at_level(logging.INFO, logger="redsun"):
        obj.logger.info("hello")
    return GlobalFormatter(datefmt=DATE_FORMAT).format(caplog.records[-1])


@pytest.mark.parametrize(
    ("obj", "expected"),
    [
        pytest.param(MockLoggable(), "[MockLoggable -> Test instance]", id="named"),
        pytest.param(LoggableNoName(), "[LoggableNoName]", id="no-name"),
        pytest.param(EmptyName(), "[EmptyName]", id="empty-name"),
    ],
)
def test_the_owner_is_named_as_far_as_it_can_be(
    obj: Loggable, expected: str, caplog: LogCaptureFixture
) -> None:
    """The name is dropped when the component declares none, or declares it empty."""
    assert _formatted(obj, caplog).endswith(f"{expected}: hello")


def test_a_record_from_the_bare_logger_names_no_owner(
    caplog: LogCaptureFixture,
) -> None:
    """Nothing went through the adapter, so there is no class and no name to show."""
    with caplog.at_level(logging.INFO, logger="redsun"):
        logger.info("hello")

    formatted = GlobalFormatter(datefmt=DATE_FORMAT).format(caplog.records[-1])
    assert formatted.endswith("[INFO]: hello")


@pytest.mark.parametrize(
    ("level", "carries_origin"),
    [
        pytest.param(logging.DEBUG, True, id="below-info"),
        pytest.param(logging.INFO, False, id="info"),
        pytest.param(logging.WARNING, True, id="above-info"),
    ],
)
def test_only_an_info_record_omits_its_origin(
    level: int, carries_origin: bool, caplog: LogCaptureFixture
) -> None:
    """An INFO line is running commentary; anything else is worth locating."""
    with caplog.at_level(logging.DEBUG, logger="redsun"):
        logger.log(level, "hello")

    record = caplog.records[-1]
    formatted = GlobalFormatter(datefmt=DATE_FORMAT).format(record)

    origin = f"(test_log.py:{record.lineno})"
    assert formatted.endswith(origin) is carries_origin


def test_one_stream_handler_is_installed() -> None:
    """One destination, through the shared formatter.

    The stream it holds is whatever ``sys.stdout`` was when `redsun.log` was
    imported, so it is not the object this process has now.
    """
    installed = [
        handler
        for handler in logger.handlers
        if isinstance(handler, logging.StreamHandler)
    ]

    assert len(installed) == 1
    assert isinstance(installed[0].formatter, GlobalFormatter)


def test_a_handler_receives_what_the_logger_passes() -> None:
    handler = RecordingHandler()
    add_handler(handler)
    try:
        logger.warning("reaches both")
    finally:
        remove_handler(handler)
    logger.warning("reaches only stdout")

    assert [record.getMessage() for record in handler.records] == ["reaches both"]


def test_a_handler_is_given_the_shared_formatter() -> None:
    handler = RecordingHandler()

    add_handler(handler)
    try:
        assert isinstance(handler.formatter, GlobalFormatter)
    finally:
        remove_handler(handler)


def test_a_handler_keeps_a_formatter_of_its_own() -> None:
    handler = RecordingHandler()
    own = logging.Formatter("%(message)s")
    handler.setFormatter(own)

    add_handler(handler)
    try:
        assert handler.formatter is own
    finally:
        remove_handler(handler)


def test_removing_a_handler_that_was_never_added_is_harmless() -> None:
    before = list(logger.handlers)

    remove_handler(RecordingHandler())

    assert logger.handlers == before


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        pytest.param(logging.DEBUG, logging.DEBUG, id="constant"),
        pytest.param("WARNING", logging.WARNING, id="name"),
        pytest.param("warning", logging.WARNING, id="lowercase-name"),
    ],
)
def test_set_level_takes_a_constant_or_a_name(
    restore_level: None, level: int | str, expected: int
) -> None:
    set_level(level)

    assert logger.level == expected


@pytest.mark.parametrize(
    ("level", "error"),
    [
        pytest.param("verbose", ValueError, id="not-a-level"),
        pytest.param(3.5, TypeError, id="neither-form"),
    ],
)
def test_set_level_refuses_what_names_no_level(
    restore_level: None, level: object, error: type[Exception]
) -> None:
    with pytest.raises(error):
        set_level(level)  # type: ignore[arg-type]
