"""Tests for the example session and the `redsun` command that runs it."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from redsun._manifest import OWN_PLUGIN
from redsun.examples import ExampleApp, example_config
from redsun.qt import QtHook
from redsun.session._plugins import manifest

if TYPE_CHECKING:
    from pathlib import Path

    from qtpy.QtWidgets import QApplication

    from redsun.testing import BuildSession


@pytest.mark.qt
@pytest.mark.parametrize("style", [None, *sorted(manifest(OWN_PLUGIN).hooks)])
def test_the_example_builds_every_component_under_each_style(
    style: str | None,
    qapp: QApplication,
    build: BuildSession,
    tmp_path: Path,
    unstyled: None,
) -> None:
    """Build the example whole and with every port connected, with the style named installed."""
    config = {**example_config(style), "storage": {"base_dir": str(tmp_path)}}

    session = build(ExampleApp, config)

    installed = session.hooks[QtHook.CONFIGURE_APPLICATION]
    assert len(installed) == (0 if style is None else 1)
    assert not session.unconnected
