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

## Install Redsun

Install from [PyPI](https://pypi.org/project/redsun/) or from the GitHub [repository](https://github.com/redsun-acquisition/redsun).

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

`redsun` needs a Qt binding. Install the one you prefer:

=== "`pyqt6`"

    ```bash
    pip install redsun[pyqt]
    ```

=== "`pyside6`"

    ```bash
    pip install redsun[pyside]
    ```

## Install development dependencies

To contribute or run the tests, install the development dependencies from the [PEP-735](https://peps.python.org/pep-0735/) dependency groups.

=== "uv (recommended)"

    ```bash
    uv sync
    ```

=== "pip"

    ```bash
    pip install -e . --group dev
    ```

The checks run through `tox`, which builds each environment from `uv.lock`:

```bash
uv run tox           # lint, both Qt type-checking legs, tests, docs
uv run tox -e tests
```

[Run tests](run-tests.md) lists what each environment covers.
