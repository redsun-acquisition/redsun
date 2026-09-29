---
icon: lucide/plug
---

# How plugins provide components

A [plugin](glossary.md#plugin) is an installed Python package that
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

A plugin lists what it offers in a [manifest](glossary.md#manifest), a YAML
file inside the package, registered in the entry point group
`redsun.plugins`. The name of the entry point is the `plugin_name` a session
file uses. Each entry of the manifest maps an id to a class, written as
`module:ClassName`. A class is imported only when a session names it, so a
plugin with Qt views costs nothing to a session that does not use them.

Besides the three layers, a manifest has two more groups. `providers` lists
classes that share values with every component without being components
themselves: each method a provider marks with [`provides`][redsun.provides]
shares a value, and its constructor receives shared values only, never the
keys of a session file. `services` lists [services](services.md) a session
can launch.

A manifest is checked when a session reads it, against a schema: one that
does not validate is left out whole. A session file entry that cannot be
resolved is left out on its own, and the session builds without it.
[ADR 14](decisions/0014-typed-session-files-and-manifests.md) records why
both files are typed.

[How to package components as a plugin](../how-to/package-a-plugin.md) writes
and registers a manifest, and [Plugin manifest](../reference/plugin-manifest.md)
lists every key.

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
