import pytest
import sys
from unittest import mock
from pathlib import Path

if sys.version_info > (3, 9):
    from importlib.metadata import EntryPoint
else:
    from importlib_metadata import EntryPoint
    

@pytest.fixture
def config_path() -> Path:
    return Path(__file__).parent / "configs"

@pytest.fixture
def importlib_str() -> str:
    if sys.version_info > (3, 9):
        return "importlib.metadata"
    else:
        return "importlib_metadata"
        
    
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
