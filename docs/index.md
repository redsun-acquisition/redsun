[![PyPI](https://img.shields.io/pypi/v/redsun.svg?color=green)](https://pypi.org/project/redsun)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/redsun)](https://pypi.org/project/redsun)
[![codecov](https://codecov.io/gh/redsun-acquisition/redsun/graph/badge.svg?token=XAL7NBIU9N)](https://codecov.io/gh/redsun-acquisition/redsun)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

# `redsun`

!!! note
    `redsun` is ready to deploy, but expect breaking changes while the API settles.

`redsun` is a [CPython] framework for building modular scientific data acquisition software.

It builds on the [Bluesky] ecosystem and makes no assumptions about hardware, so each lab can build the control software its experiments need.

`redsun` aims to:

- ship the tools to build the wheel, rather than another wheel;
- stay modular: use only the parts a job needs;
- leave data and metadata to you: you decide what they mean.

## Getting started

<div class="grid cards" markdown>

-   __Tutorials__

    ---

    Step-by-step lessons

    [Start learning :octicons-arrow-right-24:](tutorials/index.md)

-   __How-to guides__

    ---

    Recipes for common tasks

    [Browse guides :octicons-arrow-right-24:](how-to/index.md)

-   __Reference__

    ---

    API reference and changelog

    [View reference :octicons-arrow-right-24:](reference/index.md)

-   __Explanation__

    ---

    Concepts and design

    [Read explanations :octicons-arrow-right-24:](explanation/index.md)

</div>

## Quick links

- **[Installation guide](how-to/installation.md)**
- **[Statement of need](explanation/statement.md)**
- **[API reference](reference/api/container.md)**
- **[Changelog](reference/changelog.md)**

## About the documentation

The pages follow the [Diataxis](https://diataxis.fr/) layout:

- **Tutorials** teach by building something
- **How-to guides** solve one task
- **Reference** describes the API
- **Explanation** discusses concepts and decisions

## Project links

- [GitHub repository](https://github.com/redsun-acquisition/redsun)
- [PyPI package](https://pypi.org/project/redsun/)

[bluesky]: https://blueskyproject.io/bluesky/main/index.html
[cpython]: https://www.python.org/
