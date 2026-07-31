from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from redsun.log import Loggable

if TYPE_CHECKING:
    from pytest import LogCaptureFixture


class MockLoggable(Loggable):
    @property
    def name(self) -> str:
        return "Test instance"


class LoggableNoName(Loggable):
    pass


@pytest.mark.skipif(
    sys.platform == "darwin",
    reason="logger counts an additional record on macOS somehow",
)
def test_loggable(caplog: LogCaptureFixture) -> None:
    obj = MockLoggable()
    assert obj.name == "Test instance"

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
