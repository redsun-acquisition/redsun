---
icon: lucide/download
---

# How to install redsun

This page shows how to install `redsun` with the Python tools you already
use, and how to pick the optional parts your session needs. If you'd rather
follow one path step by step, the tutorials use `uv` in
[Installation](../tutorials/installation.md).

## Prerequisites

You need Python 3.11 or later.

## Create a virtual environment

A virtual environment keeps `redsun` and everything it installs apart from
your other Python projects, so their versions can't clash. Create one with the
tool you already use, and activate it before you install:

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
    # uses the Python you run this command with
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
what a session without a window needs. Everything else is an extra: an
optional part with its own dependencies, which you name in square brackets in
the install command, such as `redsun[pyqt]`. Pick your installer and the parts
you want, and copy the command. Each button says which extra it adds, what it
is for, and what it installs:

<!-- one button for each extra in pyproject.toml; tests/test_install_page.py
checks that the two agree -->
<div class="install-table" data-package="redsun">
<div class="install-row" data-role="command" role="group" aria-label="Installer">
<span class="install-label">Installer</span>
<div class="install-choices">
<button type="button" data-value="pip install">pip</button>
<button type="button" data-value="uv pip install --compile-bytecode">uv</button>
</div>
</div>
<div class="install-row" data-role="extra" role="group" aria-label="Window">
<span class="install-label">Window</span>
<div class="install-choices">
<button type="button" data-value="pyqt">PyQt6<small><code>pyqt</code>: a window, built on PyQt6</small></button>
<button type="button" data-value="pyside">PySide6<small><code>pyside</code>: a window, built on PySide6</small></button>
<button type="button" data-value="">none<small>no window: a headless session</small></button>
</div>
</div>
<div class="install-row" data-role="extra" data-multiple role="group" aria-label="Data">
<span class="install-label">Data</span>
<div class="install-choices">
<button type="button" data-value="zarr">Zarr<small><code>zarr</code>: derived products, with <code>acquire-zarr</code></small></button>
<button type="button" data-value="ome-zarr">OME-Zarr<small><code>ome-zarr</code>: derived products beside an OME-Zarr image, with <code>ome-writers</code></small></button>
<button type="button" data-value="tiled">Tiled<small><code>tiled</code>: a catalog of runs, with <code>tiled</code> and <code>ome-tiled</code></small></button>
</div>
</div>
<div class="install-row" data-role="extra" data-multiple role="group" aria-label="Development">
<span class="install-label">Development</span>
<div class="install-choices">
<button type="button" data-value="testing">Testing<small><code>testing</code>: tests for a plugin, with <code>pytest</code></small></button>
<button type="button" data-value="profile">Profiling<small><code>profile</code>: profiling a session, with <code>pyinstrument</code> and <code>py-spy</code></small></button>
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
<noscript><p>The buttons need JavaScript. Without it, write the command yourself,
such as <code>pip install "redsun[pyqt,zarr]"</code>: put the extras you want,
named in each button's small print, between the brackets, separated by
commas.</p></noscript>

With `uv`, the command adds `--compile-bytecode`, which prepares the Python
files to run while they install. `pip` does that by itself; `uv` otherwise
leaves it to the first session you start, which then takes several seconds
longer.

The guides for the optional parts are
[writing a derived product](write-a-derived-product.md),
[keeping a catalog of runs](keep-a-catalog.md),
[testing a plugin](test-a-plugin.md) and
[profiling a session](profile-a-session.md). The two development extras belong
in your project's development dependencies, not in what it needs to run.

For a session with a window, install one of the two Qt extras. `pyqt` and
`pyside` install the PyQt6 and PySide6
[bindings](../explanation/glossary.md#qt-binding), and `redsun` works with
either through `qtpy`. `pyside` installs only PySide6's essential modules, so
a project that needs one of its add-on modules, such as QtCharts or
QtMultimedia, adds `pyside6` to its own dependencies. A [headless session](run-without-a-gui.md), with no
window, needs neither.

!!! warning "The `tiled` extra on Python 3.14"

    `tiled` doesn't support Python 3.14 yet, so the `tiled` extra installs
    nothing there. Use Python 3.13 or earlier if you need a catalog.

## Check the installation

With the environment still active, run:

```bash
python -c "import redsun; print(redsun.__version__)"
```

If `redsun` is installed, this prints its version.

To change `redsun` itself, see [How to contribute](contribute.md).
