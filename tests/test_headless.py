"""A session naming no frontend needs no toolkit installed."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.sdk.helpers import kept_under

SCRIPT = Path(__file__).parent / "launchable" / "headless_session.py"

# a module mapped to None cannot be imported, as if it were not installed
WITHOUT_QT = """
import runpy, sys
sys.modules.update(
    dict.fromkeys(['qtpy', 'PyQt6', 'PySide6', 'app_model', 'magicgui'])
)
"""
RUN = f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')"


def test_a_session_runs_where_no_toolkit_is_installed(tmp_path: Path) -> None:
    """Run a session with no Qt installed, reporting the `qt` frontend as missing."""
    ran = subprocess.run(
        [sys.executable, "-c", WITHOUT_QT + kept_under(tmp_path) + RUN],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert ran.returncode == 0, ran.stderr
    assert "frontend 'qt', which cannot be imported" in ran.stdout
    assert "'pyqt'" in ran.stdout
    assert list(tmp_path.rglob("*.log")), "the session logged outside tmp_path"
