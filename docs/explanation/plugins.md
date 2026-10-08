---
icon: lucide/plug
---

# How plugins provide components

A [plugin](glossary.md#plugin) is an installed Python package that offers
components to sessions, so a session file can name a component by the plugin
it comes from, without any Python code:

```yaml
presenters:
  motor_ctrl:
    plugin_name: my-plugin
    plugin_id: motor
    step: 2.0
```

`plugin_name` and `plugin_id` say which class to make, and every other key is
an argument to its constructor. Step through the diagram to follow this entry
to the presenter it makes:

```d2 title="From a session file entry to a component"
...@diagrams/style
direction: down
entry: "session file entry\nplugin_name: my-plugin\nplugin_id: motor" {class: file; width: 280}
point: "entry point my-plugin\nin the group redsun.plugins" {class: hidden; width: 280}
manifest: "manifest of my_plugin\nmotor: my_plugin.presenters:MotorPresenter" {class: hidden; width: 380}
make: "import MotorPresenter, then\nMotorPresenter(name=motor_ctrl, step=2.0)" {class: hidden; width: 380}
entry -> point: "plugin_name" {style.opacity: 0}
point -> manifest {style.opacity: 0}
manifest -> make: "plugin_id" {style.opacity: 0}
steps: {
  1: {
    point: {
      class: step
      tooltip: "The entry point names the manifest file inside the package whose import name is the entry point's name, with each - read as _."
    }
    (entry -> point)[0].style.opacity: 1
  }
  2: {
    manifest: {
      class: file
      tooltip: "A YAML file inside the package, mapping each id to a class as module:ClassName."
    }
    (point -> manifest)[0].style.opacity: 1
  }
  3: {
    make: {
      class: current
      tooltip: "The session imports the class only now, because a session names it. Every other key of the entry is passed to the constructor."
    }
    (manifest -> make)[0].style.opacity: 1
  }
}
```

## The manifest

A plugin lists what it offers in a [manifest](glossary.md#manifest), a YAML
file inside the package. The package registers the manifest in the entry
point group `redsun.plugins`, and the name of the entry point is the
`plugin_name` a session file uses. A manifest has five groups; point at one to
read what it holds:

```d2 title="The groups of a manifest"
...@diagrams/style
grid-columns: 1
grid-gap: 16
devices: "devices\nid -> module:ClassName" {class: layer; width: 420}
presenters: "presenters\nid -> module:ClassName" {class: layer; width: 420}
views: "views\nid -> module:ClassName" {class: layer; width: 420}
providers: "providers\nid -> module:ClassName" {
  class: step
  width: 420
  tooltip: "Classes that share values with every component without being components themselves. Each method a provider marks with provides shares a value. A provider's constructor is filled by type only, never from the keys of a session file."
}
services: "services\nid -> how to launch it" {
  class: process
  width: 420
  tooltip: "Each entry gives the module to run as python -m, its arguments, the line it prints once it serves, and how long each stop step waits. A session file may override any of it."
}
```

The three [layers](glossary.md#layer) and `providers` map an id to a class.
The session imports a class only when a session names it, so a plugin with Qt
views costs nothing to a session that doesn't use them. Each method a
[provider](glossary.md#provider) marks with [`provides`][redsun.provides]
shares a [value](glossary.md#shared-value), and `services` lists the
[services](services.md) a session can launch.

When a session reads a manifest, it checks it against a schema and leaves out
the whole manifest when it doesn't validate. An entry of a session file that
can't be resolved is left out on its own, and the session builds without it.
[ADR 14](decisions/0014-typed-session-files-and-manifests.md) records why both
files are typed.

[How to package components as a plugin](../how-to/package-a-plugin.md) writes
and registers a manifest, and [Plugin manifest](../reference/plugin-manifest.md)
lists every key.

## Components from a file and from a class

A session can take components from both. The class declares the components it
wants as typed attributes, and the file adds the rest:

```python
class MyApp(QtSession):
    config = "session.yaml"

    motor_ctrl: AsPresenter[MotorPresenter]  # also configured in the file
```

```d2 title="A session built from a class and a file"
...@diagrams/style
direction: right
app: "class MyApp\nmotor_ctrl: AsPresenter[...]" {class: step; width: 260}
file: "session.yaml\nmotor_ctrl: step 2.0\nlogs: plugin redsun, id logs" {class: file; width: 260}
session: "the session" {
  motor_ctrl: {class: hidden; width: 160}
  logs: {class: hidden; width: 160}
}
app -> session.motor_ctrl: "declares" {style.opacity: 0}
file -> session.motor_ctrl: "configures" {style.opacity: 0}
file -> session.logs: "adds" {style.opacity: 0}
steps: {
  1: {
    session.motor_ctrl.class: step
    (app -> session.motor_ctrl)[0].style.opacity: 1
  }
  2: {
    session.motor_ctrl.class: current
    (file -> session.motor_ctrl)[0].style.opacity: 1
  }
  3: {
    session.motor_ctrl.class: step
    session.logs.class: current
    (file -> session.logs)[0].style.opacity: 1
  }
}
```

When a file entry has the same name as a declaration, it configures that
declaration and needs no `plugin_name`. An entry the class doesn't declare
names its plugin with both `plugin_name` and `plugin_id`, or it is left out.

## Built-in components

`redsun` is a plugin of itself, named `redsun`. It offers three
[stacks](glossary.md#stack), each a presenter and a view written to work
together, and a log window:

| id | presenter | view | for |
| --- | --- | --- | --- |
| `positioner` | `PositionerPresenter` | `PositionerView` | [moving devices by hand](../how-to/move-devices-by-hand.md) |
| `lights` | `LightPresenter` | `LightView` | [switching and dimming lights](../how-to/switch-and-dim-lights.md) |
| `acquisition` | `AcquisitionPresenter` | `AcquisitionView` | [running plans from the window](../how-to/run-plans-from-the-window.md) |
| `logs` | none | `LogView` | [showing the log](../how-to/configure-logging.md#show-the-logs-in-the-application) |

A session file names each one by `plugin_name: redsun` and its id, under
`presenters` or `views`:

```yaml
views:
  logs:
    plugin_name: redsun
    plugin_id: logs
```

In a Qt session, the log view docks at the bottom.
