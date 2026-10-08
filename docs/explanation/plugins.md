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
an argument to its constructor. Step through an entry becoming a presenter:

```d2 title="From a session file entry to a component"
...@diagrams/style
label: "A session file names a component by its plugin and its id."
direction: down
entry: |yaml
  # session.yaml
  presenters:
    motor_ctrl:
      plugin_name: mylab
      plugin_id: motor
      step: 2.0
| {class: step}
point: |toml
  # pyproject.toml of the mylab package
  [project.entry-points."redsun.plugins"]
  mylab = "redsun.yaml"
| {class: hidden}
manifest: |yaml
  # redsun.yaml inside the mylab package
  presenters:
    motor: mylab.presenters:MotorPresenter
| {class: hidden}
make: |python
  from mylab.presenters import MotorPresenter
  motor_ctrl = MotorPresenter(name="motor_ctrl", step=2.0)
| {class: hidden}
entry -> point: "plugin_name" {style.opacity: 0}
point -> manifest: "the manifest it names" {style.opacity: 0}
manifest -> make: "plugin_id" {style.opacity: 0}
steps: {
  1: {
    label: "plugin_name is the name of an entry point in the redsun.plugins group, which names the manifest inside the installed package."
    point.class: step
    (entry -> point)[0].style.opacity: 1
  }
  2: {
    label: "The manifest maps each id to a class, written as module:ClassName."
    manifest.class: step
    (point -> manifest)[0].style.opacity: 1
  }
  3: {
    label: "The session imports the class only now, because a session names it, and passes every other key of the entry to the constructor."
    make.class: current
    (manifest -> make)[0].style.opacity: 1
  }
}
```

## The manifest

A plugin lists what it offers in a [manifest](glossary.md#manifest), a YAML
file in the package registered in the entry point group `redsun.plugins`
under the `plugin_name` a session file uses. Point at one of its five groups
to read what it holds:

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

A class is imported only when a session names it, so a plugin's Qt views cost
nothing to a session that doesn't use them. A manifest that fails its schema
is left out whole; a session-file entry that can't be resolved is left out on
its own ([ADR 14](decisions/0014-typed-session-files-and-manifests.md)).
[How to package components as a plugin](../how-to/package-a-plugin.md) writes
one, and [Plugin manifest](../reference/plugin-manifest.md) lists every key.

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
label: "The class and the file both contribute to one session."
direction: right
app: |python
  class MyApp(QtSession):
      config = "session.yaml"

      motor_ctrl: AsPresenter[MotorPresenter]
| {class: step}
file: |yaml
  # session.yaml
  presenters:
    motor_ctrl:
      step: 2.0
  views:
    logs:
      plugin_name: redsun
      plugin_id: logs
| {class: step}
session: "the session" {
  motor_ctrl: {class: hidden; width: 160}
  logs: {class: hidden; width: 160}
}
app -> session.motor_ctrl: "declares" {style.opacity: 0}
file -> session.motor_ctrl: "configures" {style.opacity: 0}
file -> session.logs: "adds" {style.opacity: 0}
steps: {
  1: {
    label: "The class declares motor_ctrl and the class it is made from."
    session.motor_ctrl.class: step
    (app -> session.motor_ctrl)[0].style.opacity: 1
  }
  2: {
    label: "The file's entry of the same name configures it, with no plugin_name needed."
    session.motor_ctrl.class: current
    (file -> session.motor_ctrl)[0].style.opacity: 1
  }
  3: {
    label: "An entry the class doesn't declare adds a component, naming its plugin with both plugin_name and plugin_id."
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
