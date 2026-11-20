[![PyPI](https://img.shields.io/pypi/v/redsun.svg?color=green)](https://pypi.org/project/redsun)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/redsun)](https://pypi.org/project/redsun)
[![PyPI - Status](https://img.shields.io/pypi/status/redsun)](https://pypi.org/project/redsun)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![CI](https://github.com/redsun-acquisition/redsun/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/redsun-acquisition/redsun/actions/workflows/ci.yaml)
[![codecov](https://codecov.io/gh/redsun-acquisition/redsun/graph/badge.svg?token=XAL7NBIU9N)](https://codecov.io/gh/redsun-acquisition/redsun)
[![Documentation](https://img.shields.io/website?url=https%3A%2F%2Fredsun-acquisition.github.io%2Fredsun&label=docs)](https://redsun-acquisition.github.io/redsun)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-%23FE5196?logo=conventionalcommits&logoColor=white)](https://www.conventionalcommits.org)

# `redsun`

`redsun` is a [Python] toolkit for building your own modular software for scientific data acquisition. You describe your instrument in Python, and `redsun` assembles it into an application with a graphical interface. It builds on the [Bluesky] project, where `bluesky` runs acquisitions as plans and `ophyd-async` describes hardware as devices. `redsun` ships no hardware drivers, so the devices for your instruments come from you or from a plugin.

To learn `redsun`, start with the [tutorials], where you build one application step by step without any hardware. They assume no knowledge of `bluesky` or `ophyd-async`.

> [!NOTE]
> `redsun` is usable today, but it's still maturing, so expect breaking changes.

## Problem statement

When research depends on controlling hardware, one of the hardest problems is making different instruments work together in workflows that are reusable, reliable and documented. On top of that, the software needs an interface that people with less technical background can understand and use correctly.

That's hard because experiments keep changing. It's next to impossible to predict everything the software will finally need to do, especially when the people using it are scientists with no engineering background.

So `redsun` follows the idea of [component-based development](https://en.wikipedia.org/wiki/Component-based_software_engineering): it ships ready-made components, and you assemble and wire them for what you need.

## Component-based development (CBD)

In component-based development, each component is defined by its interface: it says what it needs to be built, and offers features that other components can use.

You put components together in a session, which builds the application for you, so you can focus on what each component does. In the example below, `mylab` stands for your own package:

```python
from collections.abc import Iterator
from typing import Annotated

from mylab.devices import MyMotor
from mylab.presenters import MyController
from mylab.views import MyView

from redsun import AsDevice, AsPresenter, AsView, Declare, Link
from redsun.qt import QtSession


class MyApp(QtSession):
    stage: Annotated[AsDevice[MyMotor], Declare(axis=["X", "Y"], egu="mm")]
    ctrl: Annotated[AsPresenter[MyController], Declare(timeout=2.0)]
    panel: AsView[MyView]

    def wire(self) -> Iterator[Link]:
        yield self.ctrl.sig_position_changed, self.panel.update_position


MyApp({"session": "my-session"}).run()
```

You declare each component once, with the arguments it needs, and `wire` says which signal reaches which slot. The session then builds everything in order and connects it.

`redsun` provides the shared code that connects components, so you can use it to ship a whole application or a single reusable component. A package that contributes components lists them in a `redsun.yaml` manifest, which `redsun` finds through a [Python entry point](https://packaging.python.org/en/latest/specifications/entry-points/) once the package is installed. An application can then be shipped as a single YAML configuration file.

As a file, the application above looks like this:

```yaml
# session.yaml
schema_version: 1.0
frontend: qt
session: my-session

devices:
  stage:
    plugin_name: mylab
    plugin_id: my_motor
    axis: ["X", "Y"]
    egu: mm

presenters:
  ctrl:
    plugin_name: mylab
    plugin_id: my_controller
    timeout: 2.0

views:
  panel:
    plugin_name: mylab
    plugin_id: my_view

wiring:
  ctrl.sig_position_changed: panel.update_position
```

The session looks up each `plugin_id` in the manifest that the contributing package ships:

```yaml
# mylab/redsun.yaml
devices:
  my_motor: mylab.devices:MyMotor
presenters:
  my_controller: mylab.presenters:MyController
views:
  my_view: mylab.views:MyView
```

Launch it with:

```python
from redsun import Session

Session.from_config("session.yaml").run()
```

> [!TIP]
> When you launch a session from a configuration file, the component packages it names (`mylab` in this example) must be installed in the environment you run it from.

## Session architecture

Each `redsun` session is a [Device-View-Presenter](https://redsun-acquisition.github.io/redsun/explanation/session/) (DVP) application with three layers: devices talk to the hardware through [`ophyd-async`](https://github.com/bluesky/ophyd-async), presenters hold the application's logic, and views show it to the user. The layout follows Model-View-Presenter, a common way to keep an interface apart from the logic behind it, with devices in place of the model. Devices form the bottom layer because `redsun` is first of all about device control.

## Documentation

The [documentation] covers everything else.

[bluesky]: https://blueskyproject.io/bluesky/main/index.html
[python]: https://www.python.org/
[documentation]: https://redsun-acquisition.github.io/redsun/
[tutorials]: https://redsun-acquisition.github.io/redsun/tutorials/

## License

`redsun` is released under the Apache 2.0 license. See the [license](./LICENSE) for the full text.
