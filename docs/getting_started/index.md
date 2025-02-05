# Getting Started

## Installation

It is reccomended to install the package in a virtual environment.

::::{tab-set}
:::{tab-item} venv
```{code-block} shell
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
:::
:::{tab-item} conda
```{code-block} shell
conda create -n redsun-env python=3.9
conda activate redsun-env
```
:::
:::{tab-item} mamba
```{code-block} shell
mamba create -n redsun-env python=3.9
mamba activate redsun-env
```
:::
::::

The package is currently not available on PyPI. You'll have to install it from source by cloning the [repository].

You'll also need to install the [Sunflare] package, Redsun's toolkit. It is currently available on PyPI.

```bash
# first install the Sunflare package...
pip install -U sunflare

# ... then clone the Redsun repository and install it
git clone https://github.com/redsun-acquisition/redsun.git
cd redsun
pip install -e .
```

## Usage

### Building the documentation

You can build the documentation by running the following command:

```bash
cd docs
make html

# for windows
make.bat html
```

You can then inspect the documentation in the `docs/_build/html` directory by opening the `index.html` file in your browser.

[conda]: https://docs.conda.io/en/latest/
[mamba]: https://mamba.readthedocs.io/en/latest/
[repository]: https://github.com/redsun-acquisition/redsun
[sunflare]: https://github.com/redsun-acquisition/sunflare
