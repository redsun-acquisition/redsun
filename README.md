[![PyPI](https://img.shields.io/pypi/v/redsun.svg?color=green)](https://pypi.org/project/redsun)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/redsun)](https://pypi.org/project/redsun)
[![codecov](https://codecov.io/gh/redsun-acquisition/redsun/graph/badge.svg?token=XAL7NBIU9N)](https://codecov.io/gh/redsun-acquisition/redsun)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

# `redsun`

A component-based, customizable application framework for scientific hardware orchestration, based on the [Bluesky] framework.

> [!NOTE]
> `redsun` is slowly reaching maturity, enough that it is safe to start being deployed. Still, expect major breaking changes as the API crystallizes.

## Problem statement

In scientific research involving device control, one of the major problems is orchestrating different hardware units to achieve reusable, reliable and documentable workflows. On top of that, such hardware orchestration should provide a coherent and understandable user interface that less technical inclined users are able to understand and leverage accurately.

This proves challenging, because making experiments is a fluid endevour. It's hard (next to impossible) to predict what are the actual final requirements a software should encapsulate, especially if the final output is to face this to scientists with no engineering background.

Rather than trying to ship an entire software on its own, `redsun` follows the idea of [**component-based development**](https://en.wikipedia.org/wiki/Component-based_software_engineering): ship off-the-shelf components, assemble and wire them depending on the needs.

## Component-based development (CBD)

In CBD, interfaces are key. Each component express what it requires to be built, as well as offering functionalities that can be leveraged by other components.

Components are wrapped into an `AppContainer` that takes care of bootstrapping the actual application for you, letting you focus on what each component should deliver.

```python
from mylab.devices import MyMotor
from mylab.presenters import MyController
from mylab.views import MyView

from redsun.containers import declare_device, declare_presenter, declare_view
from redsun.qt import QtAppContainer


class MyApp(QtAppContainer):
    stage = declare_device(MyMotor, axis=["X", "Y"], egu="mm")
    ctrl = declare_presenter(MyController, timeout=2.0)
    panel = declare_view(MyView)

    def wire(self) -> None:
        self.connect(self.ctrl.sig_position_changed, self.panel.update_position)


MyApp(session="my-session").run()
```

Each component is declared once, with the arguments it needs. `wire` says which signal reaches which method; the container builds everything in dependency order and connects it.

`redsun` provides the common glue code that each component can use to ship entire applications or single, reusable components. Leveraging [Python entry points](https://packaging.python.org/en/latest/specifications/entry-points/), an application can also be shipped as a single YAML configuration file, provided that different contributing components expose a `redsun.yaml` manifest.

So the same application can be expressed as:

```yaml
# session.yaml
schema_version: 1.0
frontend: pyqt
name: my-session

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
  - from: ctrl.sig_position_changed
    to: panel.update_position
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
from redsun.container import AppContainer

AppContainer.from_config("session.yaml").run()
```

> [!TIP]
> When launching an app container from a configuration file, make sure that your involved component packages (i.e. `mylab` in this example) are installed in the same environment where your `AppContainer` is launched.

## `AppContainer` architecture

Each `redsun` container is structured as a [Device-View-Presenter](https://redsun-acquisition.github.io/redsun/explanation/container-architecture/) (DVP) application. This resembles the Model-View-Presenter (MVP) architecture, with the difference that at the lower level of the application sits the *Device layer*, leveraging [`ophyd-async`](https://github.com/bluesky/ophyd-async), to interact with hardware components.

This is to make a clear statement: `redsun` is primarely about device control, and tries to do it well.

## Documentation

See the [documentation] for more informations.

[bluesky]: https://blueskyproject.io/bluesky/main/index.html
[documentation]: https://redsun-acquisition.github.io/redsun/

## License

`redsun` is released under license Apache 2.0.

See the [license](./LICENSE) for further details.
