---
icon: lucide/plug
---

# How plugins provide components

A [plugin](../reference/glossary.md#plugin) is an installed Python package that
offers components to sessions. A session file can then name a component by
the plugin it comes from, without any Python code:

```yaml
presenters:
  motor_ctrl:
    plugin_name: my-plugin
    plugin_id: motor
    step: 2.0
```

`plugin_name` and `plugin_id` say which class to make. Every other key is an
argument to its constructor.

## The manifest

A plugin lists what it offers in a [manifest](../reference/glossary.md#manifest),
a YAML file inside the package:

```yaml
# my_plugin/redsun.yaml
devices:
  stage: "my_plugin.devices:MyStage"

presenters:
  motor: "my_plugin.presenters:MotorPresenter"

views:
  motor-view: "my_plugin.views:MotorView"

providers:
  calibration: "my_plugin.services:Calibrations"

services:
  stage-ioc:
    module: my_plugin.iocs.stage
    ready: "Server startup complete."
```

Each entry maps an id to a class, written as `module:ClassName`. A class is
imported only when a session names it, so a plugin with Qt views costs nothing
to a session that does not use them.

The `providers` group lists classes that share values with every component,
without being components themselves. A provider's constructor is filled like
a component's, and each method it marks with [`provides`][redsun.provides]
shares a value.

The `services` group lists services a session can launch: the `module` to run
and, optionally, its `args`, the `ready` line it prints, and its
`stop_timeout`. See [Services](services.md).

The package registers the manifest as an entry point:

```toml
[project.entry-points."redsun.plugins"]
my-plugin = "redsun.yaml"
```

The entry point's name is the `plugin_name` a session file uses. Check that
your build tool puts `redsun.yaml` in the package.

An editor that reads JSON schemas can check a manifest as you write it, if its
first line names the published schema:

```yaml
# yaml-language-server: $schema=https://redsun-acquisition.github.io/redsun/reference/schemas/plugin-manifest.schema.json
```

## When something does not resolve

A manifest is checked when a session reads it. One with an unknown group, an
unknown key, or a class path not written as `module:ClassName` is left out
whole, and the log names the file and every problem.

A session file entry that cannot be resolved is left out on its own, and the
session builds without it:

- the plugin is not installed, or its manifest was left out;
- the manifest has no such id;
- the class cannot be imported;
- the entry names no plugin, and the session class declares no component of
  that name.

Each shows in the log and in the build summary under `Not built`. To stop the
session instead, make it [strict](../reference/glossary.md#strict-session).

## Components from a file and from a class

A session can mix both. A class declares the components it wants typed
attributes for; the file adds the rest:

```python
class MyApp(QtSession):
    config = "session.yaml"

    motor_ctrl: AsPresenter[MotorPresenter]  # also configured in the file
```

A file entry with the same name as a declaration configures that declaration,
and needs no `plugin_name`.

## Built-in components

`redsun` is a plugin of itself, named `redsun`. It offers one view, the log
window:

```yaml
views:
  logs:
    plugin_name: redsun
    plugin_id: logs
```

The log view docks at the bottom of a Qt session.
[Configure logging](../how-to/configure-logging.md) describes what it shows.
