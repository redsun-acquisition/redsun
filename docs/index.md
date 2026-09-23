---
icon: lucide/house
hide:
  - toc
---

[![PyPI](https://img.shields.io/pypi/v/redsun.svg?color=green)](https://pypi.org/project/redsun)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/redsun)](https://pypi.org/project/redsun)
[![codecov](https://codecov.io/gh/redsun-acquisition/redsun/graph/badge.svg?token=XAL7NBIU9N)](https://codecov.io/gh/redsun-acquisition/redsun)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

# `redsun`

!!! note "Still settling"
    `redsun` is ready to deploy, but expect breaking changes while the API settles.

`redsun` is a [CPython] framework for building modular scientific data acquisition software.

It builds on the [Bluesky] ecosystem and makes no assumptions about hardware, so each lab can build the control software its experiments need.

| What | Where |
| --- | --- |
| Source | <https://github.com/redsun-acquisition/redsun> |
| PyPI | `pip install redsun` |
| Documentation | <https://redsun-acquisition.github.io/redsun> |
| Releases | <https://github.com/redsun-acquisition/redsun/releases> |

## How the documentation is structured

The documentation is split into [four categories](https://diataxis.fr), also
reachable from the tabs at the top. Technical words are defined once, in the
[glossary](reference/glossary.md).

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

    Explanations of how `redsun` works and why it works that way.

    [:lucide-arrow-right: Explanations](explanation/index.md)

-   :lucide-book-open:{ .lg .middle } **Reference**

    ---

    Technical reference material, including the API, the glossary and the
    release notes.

    [:lucide-arrow-right: Reference](reference/index.md)

</div>

[bluesky]: https://blueskyproject.io/bluesky/main/index.html
[cpython]: https://www.python.org/
