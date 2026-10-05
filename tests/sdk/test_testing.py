"""The fixtures `redsun.testing` gives a suite keep each test to itself."""

from __future__ import annotations

from typing import TYPE_CHECKING

from redsun import Session

if TYPE_CHECKING:
    from pathlib import Path

    from redsun.testing import BuildSession


def test_a_session_keeps_its_settings_under_tmp_path(
    tmp_path: Path, build: BuildSession
) -> None:
    """Open a session's settings under `tmp_path` without requesting `config_home`."""
    session = build(Session, {"session": "kept-to-the-test"})

    assert session.settings.path.is_relative_to(tmp_path)
