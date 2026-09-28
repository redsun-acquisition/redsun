---
icon: lucide/download
---

# Installation

## Create a virtual environment

Install `redsun` in a virtual environment.

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

## Install redsun

`redsun` is on [PyPI](https://pypi.org/project/redsun/). Install it together
with the [Qt binding](../explanation/glossary.md#qt-binding) you prefer:

=== "`pyqt6`"

    ```bash
    pip install "redsun[pyqt]"

    # Or if you're using uv
    uv pip install "redsun[pyqt]"
    ```

=== "`pyside6`"

    ```bash
    pip install "redsun[pyside]"

    # Or if you're using uv
    uv pip install "redsun[pyside]"
    ```

A session that shows no window needs no Qt binding: `pip install redsun` is
enough. See [Run without a GUI](../how-to/run-without-a-gui.md).

To change `redsun` itself, see [How to contribute](../how-to/contribute.md).
