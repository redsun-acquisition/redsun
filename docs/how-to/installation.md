# Installation

This guide covers how to install Redsun in different environments.

## Create a virtual environment

It is recommended to install the package in a virtual environment.

=== "uv (recommended)"

    ```bash
    uv venv --python 3.10

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
    conda create -n redsun-env python=3.10
    conda activate redsun-env
    ```

=== "mamba"

    ```bash
    mamba create -n redsun-env python=3.10
    mamba activate redsun-env
    ```

## Install Redsun

The package is available on [PyPI](https://pypi.org/project/redsun/) or directly from the GitHub [repository](https://github.com/redsun-acquisition/redsun).

=== "PyPI"

    ```bash
    pip install -U redsun

    # Or if you're using uv
    uv pip install redsun
    ```

=== "GitHub (development)"

    ```bash
    git clone https://github.com/redsun-acquisition/redsun.git
    cd redsun
    pip install -e .
    ```

### Qt backend

Redsun requires a Qt backend. Install with your preferred binding:

=== "PyQt6"

    ```bash
    pip install redsun[pyqt]
    ```

=== "PySide6"

    ```bash
    pip install redsun[pyside]
    ```

## Install development dependencies

If you are contributing to Redsun or want to run tests locally, install the development dependencies via [PEP-735](https://peps.python.org/pep-0735/) dependency groups.

=== "uv (recommended)"

    ```bash
    uv sync
    ```

=== "pip"

    ```bash
    pip install -e .[dev]
    ```

## Next steps

- Learn how to [build the documentation](build-docs.md)
- Learn how to [run tests](run-tests.md)
- Check out the [tutorials](../tutorials/index.md) to get started with Redsun
