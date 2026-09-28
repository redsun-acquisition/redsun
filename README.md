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

A component-based, customizable application framework for scientific hardware orchestration, based on the [Bluesky] framework.

> [!NOTE]
> `redsun` can be used today. Until version 1.0, a release may change the API in ways that break existing code.

## Problem statement

In scientific research involving device control, one of the major problems is orchestrating different hardware units to achieve reusable, reliable and documentable workflows. On top of that, such hardware orchestration should provide a coherent and understandable user interface that less technical inclined users are able to understand and leverage accurately.

This proves challenging, because making experiments is a fluid endevour. It's hard (next to impossible) to predict what are the actual final requirements a software should encapsulate, especially if the final output is to face this to scientists with no engineering background.

Rather than trying to ship an entire software on its own, `redsun` follows the idea of [**component-based development**](https://en.wikipedia.org/wiki/Component-based_software_engineering): ship off-the-shelf components, assemble and wire them depending on the needs.

## Component-based development (CBD)

In CBD, interfaces are key. Each component express what it requires to be built, as well as offering functionalities that can be leveraged by other components.

Components are put together in a session, which builds the application for you, so you can focus on what each component does.

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

Each component is declared once, with the arguments it needs. `wire` says which signal reaches which slot; the session builds everything in order and connects it.

`redsun` provides the common glue code that each component can use to ship entire applications or single, reusable components. Leveraging [Python entry points](https://packaging.python.org/en/latest/specifications/entry-points/), an application can also be shipped as a single YAML configuration file, provided that different contributing components expose a `redsun.yaml` manifest.

So the same application can be expressed as:

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

`plugin_id` is resolved through the manifest the contributing package ships:

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
> When launching a session from a configuration file, make sure that the component packages it names (`mylab` in this example) are installed in the same environment.

## Session architecture

Each `redsun` session is structured as a [Device-View-Presenter](https://redsun-acquisition.github.io/redsun/explanation/session/) (DVP) application. This resembles the Model-View-Presenter (MVP) architecture, with the difference that at the lower level of the application sits the *Device layer*, leveraging [`ophyd-async`](https://github.com/bluesky/ophyd-async), to interact with hardware components.

This is to make a clear statement: `redsun` is primarely about device control, and tries to do it well.

## Documentation

See the [documentation] for more informations.

[bluesky]: https://blueskyproject.io/bluesky/main/index.html
[documentation]: https://redsun-acquisition.github.io/redsun/

## License

`redsun` is released under license Apache 2.0.

See the [license](./LICENSE) for further details.
