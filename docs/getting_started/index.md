# Getting Started

## Installation

It is reccomended to install the package in a virtual environment.

=== "venv"

    ```shell
    # python version depends
    # on the globally installed python
    python -m venv redsun-env

    venv\Scripts\activate

    # for Windows...
    # ... command prompt
    venv\Scripts\activate.bat

    # ... powershell
    venv\Scripts\Activate.ps1
    ```

=== "conda"

    ```shell
    conda create -n redsun-env python=3.9
    conda activate redsun-env
    ```

=== "mamba"

    ```shell
    mamba create -n redsun-env python=3.9
    mamba activate redsun-env
    ```

The package available on PyPI. You can install it via the following command in your active environment:

```bash
pip install -U redsun
```

Alternatively, you can install by locally cloning the repository:

```bash
git clone https://github.com/redsun-acquisition/redsun.git
cd redsun
pip install -e .
```

## Usage

### Building the documentation

If you have cloned the repository locally, you can build the documentation by running the following command:

```bash
cd docs
make html

# for windows
make.bat html
```

You can then inspect the documentation in the `docs/_build/html` directory by opening the `index.html` file in your browser.

### Running tests

If you have cloned the repository locally, you can run tests via `pytest` as follows:

```bash
pip install -e .[dev]

pytest
```

You can get a report of test coverage via the comand:

```bash
pytest --cov=redsun --cov-report=html
```

This will generate a coverage report in the folder `htmlcov`. You can inspect the report by opening the `index.html` file in your browser.

[conda]: https://docs.conda.io/en/latest/
[mamba]: https://mamba.readthedocs.io/en/latest/
[repository]: https://github.com/redsun-acquisition/redsun
[sunflare]: https://github.com/redsun-acquisition/sunflare
