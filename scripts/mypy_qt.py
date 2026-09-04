"""Run mypy with the flags qtpy computes for the binding ``QT_API`` names.

``qtpy mypy-args`` prints the ``--always-true`` / ``--always-false`` flags that
pin which of its own branches mypy reads, and those flags depend on the binding
selected at import. Composing the two needs command substitution, which
``cmd.exe`` does not have and no tox ``commands`` line can express, so this
does it in one process instead.

Arguments are passed to mypy after the flags.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    """Print the binding in use, then run mypy against it."""
    from qtpy import API_NAME
    from qtpy.cli import generate_mypy_args

    print(f"mypy against {API_NAME}", flush=True)
    return subprocess.call(
        [sys.executable, "-m", "mypy", *generate_mypy_args().split(), *sys.argv[1:]]
    )


if __name__ == "__main__":
    raise SystemExit(main())
