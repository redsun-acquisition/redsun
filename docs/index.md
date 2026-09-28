---
icon: lucide/house
hide:
  - toc
---

[![PyPI](https://img.shields.io/pypi/v/redsun.svg?color=green)](https://pypi.org/project/redsun)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/redsun)](https://pypi.org/project/redsun)
[![PyPI - Status](https://img.shields.io/pypi/status/redsun)](https://pypi.org/project/redsun)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![CI](https://github.com/redsun-acquisition/redsun/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/redsun-acquisition/redsun/actions/workflows/ci.yaml)
[![codecov](https://codecov.io/gh/redsun-acquisition/redsun/graph/badge.svg?token=XAL7NBIU9N)](https://codecov.io/gh/redsun-acquisition/redsun)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-%23FE5196?logo=conventionalcommits&logoColor=white)](https://www.conventionalcommits.org)

# `redsun`

!!! note "Still settling"
    `redsun` is ready to deploy, but expect breaking changes while the API settles.

`redsun` is a [CPython] framework for building modular scientific data acquisition software.

It builds on the [Bluesky] ecosystem and makes no assumptions about hardware, so each lab can build the control software its experiments need.

## What you get, and what you write

`redsun` is a library you build an acquisition program with. It is not a
program you open.

`redsun` gives you:

- a [session](explanation/glossary.md#session), which builds your
  [components](explanation/glossary.md#component) in order and connects them
- a [session file](explanation/glossary.md#session-file), to change settings
  without touching code
- the starting and stopping of the
  [services](explanation/glossary.md#service) your hardware sits behind
- the widgets of a [plan](explanation/glossary.md#plan), made from its
  signature
- built-in views, such as the log window
- a folder for each acquisition
- a [catalog](explanation/glossary.md#catalog) of runs, if you install it

You write, or install as a [plugin](explanation/glossary.md#plugin):

- the [devices](explanation/glossary.md#device),
  [presenters](explanation/glossary.md#presenter) and
  [views](explanation/glossary.md#view) of your setup
- the services that reach your hardware
- the plans of your acquisitions

`redsun` does not ship:

- drivers for hardware
- an acquisition panel
- an image viewer
- a writer of acquisition files

[Why redsun exists](explanation/statement.md#what-redsun-does-not-ship) says
who provides each of these, and how the parts compare with those of
Micro-Manager.

<div style="display: flex; justify-content: center" markdown>

| What | Where |
| --- | --- |
| Source | <https://github.com/redsun-acquisition/redsun> |
| PyPI | `pip install redsun` |
| Documentation | <https://redsun-acquisition.github.io/redsun> |
| Releases | <https://github.com/redsun-acquisition/redsun/releases> |

</div>

## How the documentation is structured

The documentation follows the [Diataxis](https://diataxis.fr) format. Reference
to technical terminology is shown in the [glossary](explanation/glossary.md).

<div class="grid cards" markdown>

-   :lucide-graduation-cap:{ .lg .middle } **Tutorials**

    ---

    Installation, a first working session, and what is built on it. New users
    start here.

    [:lucide-arrow-right: Tutorials](tutorials/index.md)

-   :lucide-compass:{ .lg .middle } **How-to Guides**

    ---

    Practical step-by-step guides for one task each, including working on
    `redsun` itself.

    [:lucide-arrow-right: How-to Guides](how-to/index.md)

-   :lucide-lightbulb:{ .lg .middle } **Explanations**

    ---

    Explanations of how `redsun` works and why it works that way, and the
    glossary.

    [:lucide-arrow-right: Explanations](explanation/index.md)

-   :lucide-book-open:{ .lg .middle } **Reference**

    ---

    Technical reference material: the API and the release notes.

    [:lucide-arrow-right: Reference](reference/index.md)

</div>

[bluesky]: https://blueskyproject.io/bluesky/main/index.html
[cpython]: https://www.python.org/
