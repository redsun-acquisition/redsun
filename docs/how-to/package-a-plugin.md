---
icon: lucide/package
---

# How to package components as a plugin

Ship devices, presenters and views in an installable package, so a
[session file](../explanation/glossary.md#session-file) can name them without
any Python. [How plugins provide components](../explanation/plugins.md)
explains what a [plugin](../explanation/glossary.md#plugin) is and how a
session finds one.

## Prerequisites

Components that already work when a session class declares them. See
[Write a component](write-a-component.md).

## Lay out the package

Put the components in modules of an ordinary package, with a manifest file
beside them:

```text
mylab/
|-- pyproject.toml
`-- src/mylab/
    |-- __init__.py
    |-- redsun.yaml
    |-- devices.py
    |-- presenters.py
    `-- views.py
```

## Write the manifest

List each class under its group, by an id of your choice, as
`module:ClassName`:

```yaml
# yaml-language-server: $schema=https://redsun-acquisition.github.io/redsun/reference/schemas/plugin-manifest.schema.json
devices:
  motor: "mylab.devices:MyMotor"

presenters:
  controller: "mylab.presenters:MyController"

views:
  motor-view: "mylab.views:MyView"
```

The first line lets an editor with a YAML language server check the file as
you type. [Plugin manifest](../reference/plugin-manifest.md) lists every key.

## Register the entry point

In `pyproject.toml`, register the manifest in the `redsun.plugins` group. The
value is the path of the manifest inside the package:

```toml
[project.entry-points."redsun.plugins"]
mylab = "redsun.yaml"
```

The session looks for the manifest in the package whose import name is the
entry point's name, with each `-` read as `_`. So `mylab` finds `mylab`, and
`my-lab` would look for a package `my_lab`. The entry point's name is also the
`plugin_name` a session file uses.

The manifest must be in the built package. `hatchling` includes every file
under the package folder; other build tools may need it listed as package
data. To check, build a wheel and look for `mylab/redsun.yaml` in it:

```bash
uv build --wheel
```

## Install it

Install the package into the environment that runs the session, for example
as an editable dependency of your session's project:

```bash
uv add --editable ../mylab
```

## Name the components in a session file

Each entry takes `plugin_name` and `plugin_id`. Every other key is passed to
the constructor:

```yaml
session: my-lab
frontend: qt

devices:
  x:
    plugin_name: mylab
    plugin_id: motor
    units: um

presenters:
  ctrl:
    plugin_name: mylab
    plugin_id: controller
    step: 0.5

views:
  panel:
    plugin_name: mylab
    plugin_id: motor-view
```

Build the session from the file:

```python
from redsun import Session

Session.from_config("session.yaml").run()
```

A session class can also name the file in `config` and declare some of the
components itself; an entry with the same name as a declaration configures it
and needs no `plugin_name`. See
[Components from a file and from a class](../explanation/plugins.md#components-from-a-file-and-from-a-class).

## Share a value from the plugin

A class that shares values without being a component goes under `providers`.
Mark each method returning a shared value with
[`provides`][redsun.provides]:

```python
# mylab/providers.py
from typing import NewType

from redsun import provides

Scale = NewType("Scale", float)


class MyCalibration:
    @provides
    def current_scale(self) -> Scale:
        return Scale(2.5)
```

```yaml
# mylab/redsun.yaml
providers:
  calibration: "mylab.providers:MyCalibration"
```

The session file names it in its own `providers` section:

```yaml
providers:
  calibration:
    plugin_name: mylab
    plugin_id: calibration
```

A component then asks for a `Scale` in its constructor. The provider's own
constructor is filled from the shared values only; other keys of its entry are
not passed to it. [Share a value](share-a-value.md) shows how a component
asks for one.

## List a service

A plugin can list a service a session launches, under `services` in its
manifest. See [Write a service](write-a-service.md#declare-it).

## Read a failure

A manifest that does not validate is left out whole, and the log names the
file and each problem. An entry that does not resolve is left out on its own,
and the build summary lists it under `Not built`:

```text
[ERROR]: Failed to build view 'panel': plugin 'mylab' declares no view 'motor-viwe'. Its views: motor-view
[WARNING]: Container built: 1/1 devices, 1/1 presenters, 0/1 views
Not built: panel (view)
```

To stop the build instead, make the session
[strict](../explanation/glossary.md#strict-session).
