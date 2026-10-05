"""The fixtures `redsun.testing` gives a suite keep each test to itself."""

from __future__ import annotations

from typing import TYPE_CHECKING

from redsun import Session

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from redsun.testing import BuildSession

pytest_plugins = ["pytester"]

TWO_SESSIONS = """
from pathlib import Path

from redsun import Session


def refuse() -> None:
    raise RuntimeError("the second session could not stop")


def test_two_sessions(build):
    first = build(Session, {{"session": "first"}})
    first.on_release(Path({marker!r}).touch)
    second = build(Session, {{"session": "second"}})
    second.on_release(refuse)
"""
"""A test building two sessions, whose second refuses to shut down."""


def test_a_session_keeps_its_settings_under_tmp_path(
    tmp_path: Path, build: BuildSession
) -> None:
    """Open a session's settings under `tmp_path` without requesting `config_home`."""
    session = build(Session, {"session": "kept-to-the-test"})

    assert session.settings.path.is_relative_to(tmp_path)


def test_every_session_is_shut_down_when_one_refuses(
    pytester: pytest.Pytester,
) -> None:
    """Shut the earlier session down when a later one raises, then report the error."""
    marker = pytester.path / "first-shut-down"
    pytester.makepyfile(TWO_SESSIONS.format(marker=str(marker)))

    result = pytester.runpytest("-p", "redsun.testing")

    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(["*the second session could not stop*"])
    assert marker.exists()
