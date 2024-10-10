import logging
import pytest
from redsun.toolkit.log import setup_logger, core_logger

class MockPlugin:
    def __init__(self, instance_name: str = None) -> None:
        self.logger = setup_logger(self, instance_name=instance_name)
    
    def call_info_logger(self, msg: str) -> None:
        self.logger.info(msg)
    
    def call_debug_logger(self, msg: str) -> None:
        self.logger.debug(msg)
    
    def call_error_logger(self, msg: str) -> None:
        self.logger.error(msg)
    
    def call_warning_logger(self, msg: str) -> None:
        self.logger.warning(msg)
    
    def call_critical_logger(self, msg: str) -> None:
        self.logger.critical(msg)
    
    def call_exception_logger(self, msg: str) -> None:
        try:
            raise Exception(msg)
        except Exception as e:
            self.logger.exception(e)

def test_core_logger(caplog: "logging.LogRecord", enable_log_debug) -> None:
    assert core_logger.name == 'redsun'

    core_logger.info('Test info message')
    core_logger.debug('Test debug message')
    core_logger.error('Test error message')
    core_logger.warning('Test warning message')
    core_logger.critical('Test critical message')
    try:
        raise Exception('Test exception message')
    except Exception as e:
        core_logger.exception(e)
    
    assert "Test info message" in caplog.text
    assert "Test debug message" in caplog.text
    assert "Test error message" in caplog.text
    assert "Test warning message" in caplog.text
    assert "Test critical message" in caplog.text
    assert "Test exception message" in caplog.text


def test_plugin_logger(caplog: "logging.LogRecord", enable_log_debug) -> None:
    plugin = MockPlugin()
    plugin.call_info_logger('Test info message')

    assert "Test info message" in caplog.text
    assert "[MockPlugin]" in caplog.text

    plugin.call_debug_logger('Test debug message')

    assert "Test debug message" in caplog.text
    assert "[MockPlugin]" in caplog.text

    plugin.call_error_logger('Test error message')

    assert "Test error message" in caplog.text
    assert "[MockPlugin]" in caplog.text

    plugin.call_warning_logger('Test warning message')

    assert "Test warning message" in caplog.text

    plugin.call_critical_logger('Test critical message')

    assert "Test critical message" in caplog.text
    assert "[MockPlugin]" in caplog.text

    plugin.call_exception_logger('Test exception message')

    assert "Test exception message" in caplog.text
    assert "[MockPlugin]" in caplog.text

def test_plugin_logger_instance(caplog: "logging.LogRecord", enable_log_debug) -> None:
    plugin = MockPlugin('NewPlugin')
    plugin.call_info_logger('Test info message')

    assert "Test info message" in caplog.text
    assert "[MockPlugin -> NewPlugin]" in caplog.text

    plugin = MockPlugin('NewPlugin')
    plugin.call_info_logger('Test info message')

    assert "Test info message" in caplog.text
    assert "[MockPlugin -> NewPlugin]" in caplog.text

def test_plugin_name_instance(caplog: "logging.LogRecord", enable_log_debug):
    plugin = MockPlugin('NewPlugin')
    plugin.call_info_logger('Test info message')

    assert "Test info message" in caplog.text
    assert "[MockPlugin -> NewPlugin]" in caplog.text