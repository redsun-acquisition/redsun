from unittest import mock
from importlib.metadata import entry_points, EntryPoint

def test_fake_entrypoint(mock_plugin_entry_point: EntryPoint) -> None:

    def return_entry_points(group: str) -> list[EntryPoint]:
        if group == 'redsun.plugins':
            return [mock_plugin_entry_point]

    # Create a patch for importlib.metadata.entry_points
    with mock.patch("importlib.metadata.entry_points", side_effect=return_entry_points):
        ep = entry_points(group='redsun.plugins')
        assert len(ep) == 1
