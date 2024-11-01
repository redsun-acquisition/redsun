from typing import TYPE_CHECKING

from redsun.toolkit.log import Loggable, get_logger

if TYPE_CHECKING:
    from pytest import LogCaptureFixture


class MockLoggable(Loggable):
    def __init__(self, name: str = "Test instance") -> None:
        self.__name = name

    @property
    def name(self) -> str:
        return self.__name


def test_getter():
    logger = get_logger()
    assert logger.name == "redsun"


def test_loggable(caplog: "LogCaptureFixture"):
    obj = MockLoggable()
    assert obj.name == "Test instance"

    obj.info("Test info")
    obj.debug("Test debug")
    obj.warning("Test warning")
    obj.error("Test error")
    obj.critical("Test critical")
    obj.exception("Test exception")

    assert len(caplog.handler.records) == 6
    assert "Test info" in caplog.handler.records[0].msg
    assert "Test debug" in caplog.handler.records[1].msg
    assert "Test warning" in caplog.handler.records[2].msg
    assert "Test error" in caplog.handler.records[3].msg
    assert "Test critical" in caplog.handler.records[4].msg
    assert "Test exception" in caplog.handler.records[5].msg

    assert caplog.handler.records[0].clsname == "MockLoggable"
    assert caplog.handler.records[0].uid == "Test instance"

    assert caplog.handler.records[0].levelname == "INFO"
    assert caplog.handler.records[1].levelname == "DEBUG"
    assert caplog.handler.records[2].levelname == "WARNING"
    assert caplog.handler.records[3].levelname == "ERROR"
    assert caplog.handler.records[4].levelname == "CRITICAL"
    assert caplog.handler.records[5].levelname == "ERROR"
