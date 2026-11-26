---
icon: lucide/terminal
---

# The `redsun` command

When you install `redsun`, you also get the `redsun` command, a program you
run from a terminal. You tell it what to do with a subcommand, such as
`example`. `python -m redsun` runs the same command, for an environment whose
scripts are not on the path.

```bash
redsun [--version] [SUBCOMMAND]
```

| Option or subcommand | What it does |
| --- | --- |
| `--version` | prints the installed version |
| `example` | opens the example session in your platform's look |
| `example STYLE` | opens the example session in the style named: `napari` or `qlementine` |
| `plugins` | lists the installed [plugins](../explanation/glossary.md#plugin) and what each one offers |
| `plugins --json` | prints the same list as a [report](#reports) |
| none | prints the help, which lists the subcommands |

Each subcommand has a help of its own, such as `redsun example --help`.

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

`redsun plugins` shows you which plugins this environment has, and what you
can name from each in a [session file](../explanation/glossary.md#session-file).
It prints one plugin at a time: its name, the package that installs it with
that package's version, and what its
[manifest](../explanation/glossary.md#manifest) lists. The manifest sorts
what a plugin offers into groups, such as `devices` and `views`, and gives
each one a short name, its id:

```text
mylab (mylab-devices 1.2.0)
  devices: motor
  presenters: controller
  views: motor-view
```

Here `mylab` is what you write as `plugin_name`, and each id is what you
write as `plugin_id`. The package is named because its name can differ from
the plugin's: `mylab-devices` is what you install, and `mylab` is what a
session file names.

!!! warning "A plugin that was left out doesn't change the exit code"

    When a plugin's manifest can't be read or is invalid, `redsun` leaves
    the whole plugin out, and the command still exits with 0. It lists that
    plugin last, under `Skipped:`, with the reason. In a script, read
    `problems` in the [report](#reports) rather than the exit code.

## Reports

A [report](../explanation/glossary.md#report) is what a subcommand prints
when you give it `--json`, so that a program can read the answer where you
would read the text. Every report is one JSON object, and it starts with the same
three keys:

| Key | Holds |
| --- | --- |
| `redsun` | the version of `redsun` that wrote the report |
| `format` | the format of the report, `1` today |
| `problems` | what the command found wrong, each with a `kind`, `where` it was found and a `message`; empty when nothing is |

`format` is a number that tells your program whether it can still read the
report. The number gets bigger when a key is removed or changes meaning.
Adding a key leaves the number as it is, so write your program to skip the
keys it doesn't know.

The report of `redsun plugins --json` adds `plugins`, one object for each
plugin whose manifest was read without a problem:

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

`distribution` is the package that installs the plugin, and `version` is that
package's version. Each entry names its class as `class`, written
`module:ClassName`. A service has no class, so its entry has `module`
instead, the module the service is run from.

A plugin that was left out isn't in `plugins`. It's one of the `problems`,
with `manifest` as its `kind` and the plugin's name as `where`.

Each report has a JSON Schema, a file that says exactly which keys the report
can hold. The one for this report is published as
[`plugins-report.schema.json`](schemas/plugins-report.schema.json), written
in JSON Schema 2020-12.

## Exit codes

| Code | When |
| --- | --- |
| 0 | the help, the version or the plugins were printed, or the example's window was closed |
| 1 | the example could not start |
| 2 | an option or a style the command does not know |
