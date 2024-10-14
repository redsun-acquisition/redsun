import pytest
import logging

@pytest.fixture
def enable_log_debug():
    logging.getLogger().setLevel(logging.DEBUG)