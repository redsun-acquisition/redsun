[![PyPI](https://img.shields.io/pypi/v/redsun.svg?color=green)](https://pypi.org/project/redsun)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/redsun)](https://pypi.org/project/redsun)
[![codecov](https://codecov.io/gh/redsun-acquisition/redsun/graph/badge.svg?token=XAL7NBIU9N)](https://codecov.io/gh/redsun-acquisition/redsun)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

# Redsun

!!! warning
    This project is currently under active development and it may (and most likely will) receive breaking changes. Use at your own risk.

Redsun is an acquisition software written in [CPython], with the concept of building modular user interfaces for scientific data acquisition.

It leverages the [Bluesky] ecosystem to provide a flexible, hardware-agnostic and unopinionated framework for building a control software tailored to the specific needs of different users in different scientific fields.

The philosophy of Redsun is to:

- not "reinvent the wheel", but rather "ship the tools to build the wheel";
- be extensible and modular: pick only the tools you need to get the job done;
- give the control of your data (and metadata) to you: you decide what is what.

## Contents

```{toctree}
:maxdepth: 1

getting_started/index
changelog
```

[bluesky]: https://blueskyproject.io/bluesky/main/index.html
[cpython]: https://www.python.org/
