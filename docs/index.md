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

    Installation and a first working session. New users start here.

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
