"""A writer package that is missing is named with the extra installing it."""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("package", "module", "extra"),
    [
        ("acquire_zarr", "redsun.storage.writers", "redsun[zarr]"),
        ("ome_writers", "redsun.storage.writers._ome_writers", "redsun[ome-zarr]"),
    ],
)
def test_a_missing_package_names_the_extra(
    package: str, module: str, extra: str
) -> None:
    """The import says what to install, in a process without the package."""
    # None in sys.modules makes any import of the package raise ImportError
    code = f"import sys; sys.modules[{package!r}] = None; import {module}"

    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )

    assert result.returncode != 0
    assert f"ImportError: {package.replace('_', '-')}" in result.stderr
    assert f"pip install {extra}" in result.stderr
