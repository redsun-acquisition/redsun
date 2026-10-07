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

Components that already work when a session class declares them; see
[Write a component](write-a-component.md).

## Lay out the package

Put the components in modules of an ordinary package, with a manifest file
beside them. The package depends on `redsun`, and on what its components
import:

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
`plugin_name` a session file uses. Leave the `name` key out of the manifest, or
give it the entry point's name, because the session skips a manifest that
names itself otherwise.

The manifest must be in the built package. `hatchling` includes every file
under the package folder, but other build tools may need it listed as package
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

An editable install reads the entry points once. After changing them, install
the package again:

```bash
uv sync --reinstall-package mylab
```

## Name the components in a session file

Each entry takes `plugin_name` and `plugin_id`. Every other key is passed to
the constructor, so here `MyMotor` takes `units` and `MyController` takes
`step`:

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
from redsun.qt import QtSession

QtSession.from_config("session.yaml").run()
```

A session class can also name the file in `config` and declare some of the
components itself; an entry with the same name as a declaration configures it
and needs no `plugin_name`. See
[Components from a file and from a class](../explanation/plugins.md#components-from-a-file-and-from-a-class).

## Share a value from the plugin

List a provider class under `providers`, and name it in the session file as
[Share a value](share-a-value.md#share-a-value-no-component-owns) shows:

```yaml
# mylab/redsun.yaml
providers:
  calibration: "mylab.providers:MyCalibration"
```

Other keys of the session file's entry are not passed to the provider.

## List a service

A plugin can list a service a session launches, under `services` in its
manifest. See [Write a service](write-a-service.md#declare-it).

## Read a failure

The session leaves out a manifest that doesn't validate, and the log names the
file and each problem. An entry that doesn't resolve is left out on its own,
and the build summary lists it under `Not built`:

```text
[29-09-26|08:42:44][ERROR]: Failed to build view 'panel': plugin 'mylab' declares no view 'motor-viwe'. Its views: motor-view
[29-09-26|08:42:44][WARNING]: Session built: 1/1 devices, 1/1 presenters, 0/1 views
Not built: panel (view)
```

[How to find out why a component is missing](find-a-missing-component.md)
covers reading the log, and making the session stop instead.
