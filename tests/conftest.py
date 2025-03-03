import pytest
import sys
from unittest import mock
from pathlib import Path

if sys.version_info < (3, 10):
    from importlib_metadata import EntryPoint
else:
    from importlib.metadata import EntryPoint

if sys.version_info < (3, 10):
    # this is a little hack;
    # bluesky depends on opentelemetry;
    # in version 3.9, open_telemetry
    # uses entry_points to load some internal
    # plugin; since we're mocking entry_points,
    # this call causes an error;
    # we trigger it on the first call to ensure
    # that the exception is caught and ignored;
    # this should be addressed by simply
    # marking side_effect as a fixture;
    # but it'll be done at a later date
    from opentelemetry.context import _load_runtime_context

    try:
        _load_runtime_context()
    except Exception as e:
        ...

@pytest.fixture
def config_path() -> Path:
    return Path(__file__).parent / "configs"

@pytest.fixture
def importlib_str() -> str:
    if sys.version_info < (3, 10):
        return "importlib_metadata"
    else:
        return "importlib.metadata"
    
def mock_plugin_entry_point() -> mock.Mock:
    """Set up mock entry points for testing."""

    # Create a mock entry point
    mock_entry_point = mock.Mock(spec=EntryPoint)
    mock_entry_point.name = "mock-pkg"
    mock_entry_point.value = "redsun.yaml"
    mock_entry_point.group = "redsun.plugins"
    
    # Set up the module's file attribute to point to our mock package
    manifest_path = Path(__file__).parent / "mock_pkg" / mock_entry_point.value
    mock_entry_point.load.return_value = manifest_path

    return mock_entry_point


def side_effect(group: str) -> list[EntryPoint]:
    if group == 'redsun.plugins':
        return [mock_plugin_entry_point()]
