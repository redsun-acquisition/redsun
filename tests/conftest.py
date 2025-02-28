import pytest
from importlib.metadata import EntryPoint
from pathlib import Path
from unittest import mock

@pytest.fixture
def mock_plugin_entry_point():
    """Set up mock entry points for testing."""

    # Create a mock entry point
    mock_entry_point = mock.Mock(spec=EntryPoint)
    mock_entry_point.name = "mock-pkg"
    mock_entry_point.value = "manifest.yaml"
    mock_entry_point.group = "redsun.plugins"
    
    # Set up the module's file attribute to point to our mock package
    mock_pkg_dir = Path(__file__).parent / "mock_pkg"
    manifest_path = mock_pkg_dir / "redsun.yaml"
    mock_entry_point.load.return_value = manifest_path
    
    return [mock_entry_point]

@pytest.fixture
def mock_importlib():
    """Mock importlib to return real classes from custom locations."""
    with mock.patch('importlib.import_module') as mock_import:
        def side_effect():
            import sys
            from pathlib import Path
            
            tests_dir = Path(__file__).parent.absolute()
            
            # add the mock_pkg directory to the Python path
            mock_pkg_path = tests_dir / "mock_pkg"
            if str(mock_pkg_path) not in sys.path:
                sys.path.insert(0, str(mock_pkg_path))
            
            from .mock_pkg.model import MyModel, MyModelInfo
            
            # create a module-like object to return
            class MockModule:
                pass
            
            mock_module = MockModule()
            setattr(mock_module, "MyModel", MyModel)
            setattr(mock_module, "MyModelInfo", MyModelInfo)
            
            return mock_module
        
        mock_import.side_effect = side_effect
        yield mock_import
