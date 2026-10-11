---
icon: lucide/terminal
---

# The `redsun` command

Installing `redsun` installs a command of the same name. `python -m redsun`
runs it too, for an environment whose scripts are not on the path.

```bash
redsun [--version] [--example [STYLE]]
```

| Option | What it does |
| --- | --- |
| `--version` | prints the installed version |
| `--example` | opens the example session in your platform's look |
| `--example STYLE` | opens the example session in the style named: `napari` |
| none | prints the help |

## The example session

The example is a [`QtSession`][redsun.qt.QtSession] holding every component
`redsun` ships: the acquisition, positioner, lights and log views, with
their presenters. A stage with two axes, a focus axis, a laser and an LED
stand in for hardware, so nothing outside the process moves. One plan,
`walk`, steps the focus.

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

## Exit codes

| Code | When |
| --- | --- |
| 0 | the help or the version was printed, or the example's window was closed |
| 1 | the example could not start |
| 2 | an option or a style the command does not know |
