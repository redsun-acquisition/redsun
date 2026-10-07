---
icon: lucide/download
---

# How to install redsun

You can install `redsun` with the tools you already use, adding the extras
your session needs. The tutorials show only one way, in
[Installation](../tutorials/installation.md).

## Prerequisites

You need Python 3.11 or later.

## Create a virtual environment

=== "uv (recommended)"

    ```bash
    uv venv --python 3.11

    # For Linux/macOS
    source .venv/bin/activate

    # For Windows Command Prompt
    .venv\Scripts\activate.bat

    # For Windows PowerShell
    .venv\Scripts\Activate.ps1
    ```

=== "venv"

    ```bash
    # Python version depends on the globally installed Python
    python -m venv redsun-env

    # For Linux/macOS
    source redsun-env/bin/activate

    # For Windows Command Prompt
    redsun-env\Scripts\activate.bat

    # For Windows PowerShell
    redsun-env\Scripts\Activate.ps1
    ```

=== "conda"

    ```bash
    conda create -n redsun-env python=3.11
    conda activate redsun-env
    ```

=== "mamba"

    ```bash
    mamba create -n redsun-env python=3.11
    mamba activate redsun-env
    ```

## Choose the extras

`redsun` is on [PyPI](https://pypi.org/project/redsun/). On its own it installs
what a session without a window needs, and you add everything else as an extra
by naming it in the command:

<!-- one button for each extra in pyproject.toml; tests/test_install_page.py
checks that the two agree -->
<div class="install-table" data-package="redsun">
<div class="install-row" data-role="command" role="group" aria-label="Installer">
<span class="install-label">Installer</span>
<div class="install-choices">
<button type="button" data-value="pip install">pip</button>
<button type="button" data-value="uv pip install">uv</button>
</div>
</div>
<div class="install-row" data-role="extra" role="group" aria-label="Window">
<span class="install-label">Window</span>
<div class="install-choices">
<button type="button" data-value="pyqt">PyQt6</button>
<button type="button" data-value="pyside">PySide6</button>
<button type="button" data-value="">none</button>
</div>
</div>
<div class="install-row" data-role="extra" data-multiple role="group" aria-label="Data">
<span class="install-label">Data</span>
<div class="install-choices">
<button type="button" data-value="zarr">Zarr</button>
<button type="button" data-value="ome-zarr">OME-Zarr</button>
<button type="button" data-value="tiled">Tiled</button>
</div>
</div>
<div class="install-row">
<span class="install-label">Command</span>
<div class="install-result">
<code class="install-command" aria-live="polite">pip install "redsun[pyqt]"</code>
<button type="button" class="install-copy" hidden>Copy</button>
</div>
</div>
</div>
<noscript><p>The buttons need JavaScript. Without it, write the command from the
table below: the extras you want, between the brackets and separated by
commas.</p></noscript>

| Extra | Installs | You need it for |
| --- | --- | --- |
| `pyqt` | `pyqt6`, and what the Qt widgets of `redsun` are built on | a session with a window |
| `pyside` | `pyside6`, and what the Qt widgets of `redsun` are built on | a session with a window |
| `zarr` | `acquire-zarr` | [writing a derived product](write-a-derived-product.md) |
| `ome-zarr` | `ome-writers` | writing a derived product beside an OME-Zarr image |
| `tiled` | `tiled` and `ome-tiled` | [keeping a catalog of runs](keep-a-catalog.md) |
| `testing` | `pytest` | [testing a plugin](test-a-plugin.md), as a development dependency |
| `profile` | `pyinstrument` and `py-spy` | [profiling a session](profile-a-session.md), as a development dependency |

`redsun` supports the PyQt6 and PySide6
[bindings](../explanation/glossary.md#qt-binding) through `qtpy`. Install one
of them to create a Qt session. A [headless session](run-without-a-gui.md)
doesn't need either.

!!! warning "The `tiled` extra on Python 3.14"

    `tiled` doesn't support Python 3.14 yet, so the `tiled` extra installs
    nothing there. Use Python 3.13 or earlier if you need a catalog.

## Check the installation

```bash
python -c "import redsun; print(redsun.__version__)"
```

It prints the version you installed.

To change `redsun` itself, see [How to contribute](contribute.md).
