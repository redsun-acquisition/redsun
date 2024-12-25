# Getting Started

## Installation

It is reccomended to install the package in a virtual environment.

```bash
python -m venv venv

# activate the virtual environment in Linux/MacOS
source venv/bin/activate

# activate the virtual environment in Windows
# command prompt
venv/Scripts/activate.bat

# powershell
./venv/Scripts/Activate.ps1
```

Alternatively, you can also use [`conda`] or [`mamba`] to create a new environment.

```bash
conda create -n redsun python=3.12
conda activate redsun
```

The package is currently not available on PyPI. You'll have to install it from source by cloning the [repository].

You'll also need to install the [SunFlare] package, RedSun's toolkit. It is currently available on PyPI.

```bash
# first install the SunFlare package...
pip install sunflare

# ... then clone the RedSun repository and install it
git clone https://github.com/redsun-acquisition/redsun.git
cd redsun
pip install -e .
```

## Usage

### Building the documentation

You can build the documentation by running the following command:

```bash
cd docs
make dirhtml

# for windows
make.bat dirhtml
```

You can then inspect the documentation in the `docs/_build/dirhtml` directory by opening the `index.html` file in your browser.

[conda]: https://docs.conda.io/en/latest/
[mamba]: https://mamba.readthedocs.io/en/latest/
[repository]: https://github.com/redsun-acquisition/redsun
[sunflare]: https://github.com/redsun-acquisition/sunflare
