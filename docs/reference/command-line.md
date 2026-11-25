---
icon: lucide/terminal
---

# The `redsun` command

Installing `redsun` installs a command of the same name. `python -m redsun`
runs it too, for an environment whose scripts are not on the path.

```bash
redsun [--version] [COMMAND]
```

| Option or command | What it does |
| --- | --- |
| `--version` | prints the installed version |
| `example` | opens the example session in your platform's look |
| `example STYLE` | opens the example session in the style named: `napari` or `qlementine` |
| `plugins` | lists the installed [plugins](../explanation/glossary.md#plugin) and what each one offers |
| `plugins --json` | prints the same list as a [report](#reports) |
| none | prints the help, which lists the commands |

Each command has a help of its own, such as `redsun example --help`.

## The example session

The example is a [`QtSession`][redsun.qt.QtSession] holding every component
`redsun` ships: the acquisition, positioner, lights and log views, with
their presenters. A stage with two axes, a focus axis, a laser and an LED
stand in for hardware, so nothing outside the process moves. One plan,
`walk`, sends the focus to a few positions in turn with a pause after each,
and holds it locked while it runs. The log view is a tab in the centre of
the window, and the other views are docked around it. The session class and
the function making its configuration are in `redsun.examples`.

The example needs a Qt binding, which the `pyqt` and `pyside` extras install.
Without one the command says which extra to install and exits with 1. It
exits with 1 as well when the session cannot be built, and prints the
reason.

It is a session like any other, named `redsun-example`, so it writes its
[log files](log-files.md) where every session does.

::: redsun.examples.ExampleApp
    options:
      show_root_heading: true

::: redsun.examples.example_config
    options:
      show_root_heading: true

## The installed plugins

`redsun plugins` prints each installed plugin whose
[manifest](plugin-manifest.md) loaded, with the distribution that installs it
and its version, then the ids it lists under each group:

```text
mylab (mylab-devices 1.2.0)
  devices: motor
  presenters: controller
  views: motor-view
```

`mylab` is the `plugin_name` a session file gives, and each id is a
`plugin_id`. A plugin whose manifest was left out is listed last, under
`Skipped:`, with the reason. The command exits with 0 in that case too,
because the list itself was made.

## Reports

A command that takes `--json` prints a report: one JSON object, written for a
program to read. Every report starts with the same three keys:

| Key | Holds |
| --- | --- |
| `redsun` | the version of `redsun` that wrote the report |
| `format` | the format of the report, `1` today |
| `problems` | what the command found wrong, each with a `kind`, `where` it was found and a `message`; empty when nothing is |

`format` goes up when a key is removed or changes meaning. A new key leaves
it as it is, so a program reading a report should ignore keys it does not
know.

The report of `redsun plugins --json` adds `plugins`:

```json
{
  "redsun": "0.19.0",
  "format": 1,
  "problems": [],
  "plugins": [
    {
      "plugin_name": "mylab",
      "distribution": "mylab-devices",
      "version": "1.2.0",
      "entries": [
        {"group": "devices", "plugin_id": "motor", "class": "mylab.devices:MyMotor"},
        {"group": "services", "plugin_id": "stage-ioc", "module": "mylab.iocs.stage"}
      ]
    }
  ]
}
```

An entry has `class`, as `module:ClassName`, or `module` for a service. A
plugin whose manifest was left out is not in `plugins`: it is a problem of
kind `manifest`, with the plugin's name as `where`.

The JSON Schema of each report is a file in the
[`schemas`](https://github.com/redsun-acquisition/redsun/tree/main/schemas)
folder of the repository, written in JSON Schema 2020-12.

## Exit codes

| Code | When |
| --- | --- |
| 0 | the help, the version or the plugins were printed, or the example's window was closed |
| 1 | the example could not start |
| 2 | an option or a style the command does not know |
