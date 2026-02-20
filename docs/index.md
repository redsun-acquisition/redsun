[![PyPI](https://img.shields.io/pypi/v/redsun.svg?color=green)](https://pypi.org/project/redsun)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/redsun)](https://pypi.org/project/redsun)
[![codecov](https://codecov.io/gh/redsun-acquisition/redsun/graph/badge.svg?token=XAL7NBIU9N)](https://codecov.io/gh/redsun-acquisition/redsun)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

# Redsun

**Event-driven data acquisition software for scientific applications**

!!! warning
    This project is currently under active development and it may (and most likely will) receive breaking changes. Use at your own risk.

Redsun is an acquisition software written in [CPython], with the concept of building modular user interfaces for scientific data acquisition.

It leverages the [Bluesky] ecosystem to provide a flexible, hardware-agnostic and unopinionated framework for building a control software tailored to the specific needs of different users in different scientific fields.

The philosophy of Redsun is to:

- not "reinvent the wheel", but rather "ship the tools to build the wheel";
- be extensible and modular: pick only the tools you need to get the job done;
- give the control of your data (and metadata) to you: you decide what is what.

## Getting started

<div class="grid cards" markdown>

-   __Tutorials__

    ---

    Learn Redsun from the ground up with step-by-step lessons

    [Start learning :octicons-arrow-right-24:](tutorials/index.md)

-   __How-to guides__

    ---

    Practical guides for common tasks and problems

    [Browse guides :octicons-arrow-right-24:](how-to/index.md)

-   __Reference__

    ---

    Technical documentation and API reference

    [View reference :octicons-arrow-right-24:](reference/index.md)

-   __Explanation__

    ---

    Understand the concepts and design behind Redsun

    [Read explanations :octicons-arrow-right-24:](explanation/index.md)

</div>

## Quick links

- **[Installation guide](how-to/installation.md)** - Get Redsun up and running
- **[Statement of need](explanation/statement.md)** - Why Redsun exists
- **[API reference](reference/api/config.md)** - Explore the complete API
- **[Changelog](reference/changelog.md)** - See what's new

## About the documentation

This documentation follows the [Diataxis](https://diataxis.fr/) framework, organizing content into four distinct categories based on your needs:

- **Tutorials** are learning-oriented lessons
- **How-to guides** are task-oriented recipes
- **Reference** is information-oriented technical descriptions
- **Explanation** is understanding-oriented discussions

## Project links

- [GitHub repository](https://github.com/redsun-acquisition/redsun)
- [PyPI package](https://pypi.org/project/redsun/)
- [`sunflare` repository](https://redsun-acquisition.github.io/sunflare/)

[bluesky]: https://blueskyproject.io/bluesky/main/index.html
[cpython]: https://www.python.org/
