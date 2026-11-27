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
| `describe PLUGIN [ID]` | describes the keys each device, presenter and view of a plugin takes |
| `describe PLUGIN [ID] --json` | prints the same description as a [report](#reports) |
| `check FILE...` | checks whether the session the files describe would build, without building it |
| `check FILE... --json` | prints the same check as a [report](#reports) |
| `run FILE...` | runs the session the files describe, with the frontend they name |
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

## Describing a plugin's components

`redsun describe` tells you which keys you can write in a session-file entry
for each device, presenter and view of a plugin, and what the session fills
by itself. It imports the plugin's classes and reads their constructors, so
run it in the environment the session runs in. Give it an id as well to
describe one entry only:

```bash
redsun describe mylab
redsun describe mylab controller --json
```

It prints one block for each component, a line for each key, and then the
parameters the session fills:

```text
mylab
  presenters/controller (mylab.controllers:MyController)
    workers: integer or null = null
    step: number = 1.0
    mode: one of fast, fine = "fine"
    the session fills: devices (redsun.DeviceMapping)
```

A key has the type the constructor annotates it with, and its default, or
says whether you must give it. Some keys come from the session file itself
rather than the constructor: `workers` for a presenter or a view,
`placement` and `title` for a view, and `service`, `services` and
`autoconnect` for a device. A device's required keyword can also come from a
service, so its line ends in "or from a service".

The session fills a parameter whose type a file can't write, such as the
devices or the session's settings, by looking it up by that type. A
parameter written as a `pydantic` model, a dataclass or a `TypedDict` is
listed both as a key and among what the session fills: a provider of the
session may share a value of that type, and when none does, the file has to
give it.

A component that the session couldn't build fails, with the reason in place
of its keys. That happens when its class can't be imported, when an
annotation names something that exists only for a type checker, or when a
parameter can only be given by position.

## Checking a session file

`redsun check` tells you whether a session file would build, without building
it. It reads the files with the code a build reads them with, merged in the
order you give them, but it starts no service, connects no device, opens no
window and writes no log file:

```bash
redsun check session.yaml
redsun check session.yaml this-computer.yaml --json
```

The check resolves each plugin and imports each class, so it needs the same
packages installed as the session would: checking a file whose `frontend` is
`qt` needs a Qt binding, for example. It gives each component, service and
hook provider a status, and each name the file looks up in `layout`,
`wiring`, `pairs` or a stack:

| Status | Means |
| --- | --- |
| `passed` | it would be built, or found |
| `failed` | it would not, for one of these reasons: its plugin or class can't be found, its declaration is refused, its entry gives a key its class doesn't take, it names a service the session doesn't declare, a service or provider entry's plugin can't be found, a hook provider can't be built, a wiring path is malformed or names a component the session doesn't declare or won't build, a pair names such a component, or a `layout` name has no view to answer to |
| `undecided` | reading the classes can't settle it, such as a port a class doesn't declare, which may still be a member of a [`SignalGroup`][psygnal.SignalGroup] made when the component is built |

```text
problems:
  presenters.p.workers: Input should be greater than or equal to 1
components:
  passed     devices    stage   (mylab:motor, mylab.devices:MyMotor)
  failed     views      viewer   (mylab:viewer) - plugin 'mylab' is not installed, or its manifest is invalid
lookups:
  undecided  wiring     camera.sig_frame -> viewer.show - 'camera' declares no signal 'sig_frame'; its signals: sig_done
not checked:
  the values given to constructors, what setup does, ...
```

Some things only a build can find, and the check lists them under
`not checked`: the values given to constructors, what `setup` does, members of
a `SignalGroup`, placements a view gives through a property, and services and
device connections, which never start. A file that passes the check can still
fail to build for one of those reasons.

The check exits with 1 when the file has a problem or anything `failed`. A
result that is only `undecided` exits with 0, since nothing is certainly
wrong, and is listed so that you can look at it.

## Running a session file

`redsun run` starts a session from
[session files](../explanation/glossary.md#session-file), so you don't need a
Python script to open one. It merges the files in the order you give them,
as [`Session.from_config`][redsun.Session.from_config] does, so a later file
changes what an earlier one says, and the
[frontend](../explanation/glossary.md#frontend) the files name decides what
opens:

```bash
redsun run session.yaml
redsun run session.yaml this-computer.yaml --mock
```

The options set what a script would pass to `from_config` or write as a key
of the file:

| Option | What it does |
| --- | --- |
| `--mock` | adds `mock: true` after the files, which makes it a [mocked session](../explanation/glossary.md#mocked-session) |
| `--strict` | adds `strict: true` after the files, which makes it a [strict session](../explanation/glossary.md#strict-session) |
| `--log-level LEVEL` | sets the level the session logs at, such as `DEBUG` |
| `--profile start` or `--profile run` | profiles the session's start or its whole run, as [Profile a session](../how-to/profile-a-session.md) shows |
| `--profile-dir PATH` | names the folder the profile is written to |

The command runs a session that has a frontend. A file naming no `frontend`
describes a session with nothing to show, so the command refuses it, exits
with 1 and lists the frontends installed. You start such a session from
Python instead, as [Run a session without a GUI](../how-to/run-without-a-gui.md)
shows. The command also exits with 1, printing the reason, when a file can't
be read or the session can't be built.

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

The report of `redsun describe --json` adds `plugin_name` and `components`.
Each component holds the JSON Schema of the keys its entry takes, as
`schema`, so a program can draw a form from it and check an entry against
it:

```json
{
  "redsun": "0.19.0",
  "format": 1,
  "problems": [],
  "plugin_name": "mylab",
  "components": [
    {
      "group": "presenters", "plugin_id": "controller",
      "class": "mylab.controllers:MyController", "status": "passed",
      "schema": {
        "type": "object", "additionalProperties": false,
        "properties": {
          "plugin_name": {"const": "mylab"}, "plugin_id": {"const": "controller"},
          "step": {"type": "number", "exclusiveMinimum": 0, "default": 1.0,
                   "title": "Step", "unit": "um"}
        },
        "required": ["plugin_name", "plugin_id"]
      },
      "session": [{"name": "devices", "type": "redsun.DeviceMapping", "required": true, "file": false}]
    }
  ]
}
```

A parameter's `title`, `description` and `unit` in the schema come from its
annotation, as [Write a component](../how-to/write-a-component.md) shows.
Each `session` record has `file: true` when the file may give the value
instead. A failed component has a `reason`, and no `schema` when its class
couldn't be imported. Its `problems` can have one more kind than a plugin
listing's: `parameter`, a constructor parameter that can't be described,
with `plugin_id.parameter` as `where`. An unknown plugin or id is a
`manifest` problem.

The report of `redsun check --json` adds `components`, `lookups` and
`skipped`:

```json
{
  "redsun": "0.19.0",
  "format": 1,
  "problems": [
    {"kind": "value", "where": "presenters.p.workers", "message": "Input should be greater than or equal to 1"}
  ],
  "components": [
    {"name": "stage", "group": "devices", "plugin_name": "mylab", "plugin_id": "motor",
     "class": "mylab.devices:MyMotor", "status": "passed"}
  ],
  "lookups": [
    {"section": "wiring", "name": "camera.sig_frame -> viewer.show", "status": "undecided",
     "reason": "'camera' declares no signal 'sig_frame'; its signals: sig_done"}
  ],
  "skipped": ["the values given to constructors", "what setup does"]
}
```

Its `problems` can have two more kinds than a plugin listing's: `value`, a
value of the file that is refused, with its key path as `where`, and
`session`, a session that can't be made or read at all, such as one naming a
frontend that isn't installed. After a `session` problem, `components` and
`lookups` are empty, because the check stopped where the build would.

Each report has a JSON Schema, a file that says exactly which keys the report
can hold. They are published as
[`plugins-report.schema.json`](schemas/plugins-report.schema.json),
[`describe-report.schema.json`](schemas/describe-report.schema.json) and
[`check-report.schema.json`](schemas/check-report.schema.json), written in
JSON Schema 2020-12.

## Exit codes

| Code | When |
| --- | --- |
| 0 | the help, the version or the plugins were printed, a description or a check found nothing that failed, or the window of the example or of the session run was closed |
| 1 | the example or the session run could not start, the files name no frontend, or a description or a check found a problem or something that failed |
| 2 | an option or a style the command does not know |
