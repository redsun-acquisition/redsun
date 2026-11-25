---
icon: lucide/terminal
---

# The `redsun` command

Installing `redsun` installs a command of the same name. `python -m redsun`
runs it too, for an environment whose scripts are not on the path.

```bash
redsun [--version] [--example [STYLE]] [--web]
```

| Option | What it does |
| --- | --- |
| `--version` | prints the installed version |
| `--example` | opens the example session in your platform's look |
| `--example STYLE` | opens the example session in the style named: `napari` or `qlementine` |
| `--example --web` | serves the example session over HTTP on `127.0.0.1:8000` instead of opening a window, until Ctrl+C |
| none | prints the help |

`--web` is refused without `--example`, and together with a style.

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

With `--web`, the same devices and presenters are built on
[`FastAPISession`][redsun.fastapi.FastAPISession], with no views. The
positioner and the lights are served as routes under `/api`, and
`http://127.0.0.1:8000/docs` lists them;
[How to serve a session over the web](../how-to/serve-a-session-over-the-web.md)
explains the routes. This needs the `fastapi` extra and no Qt binding.
Without the extra the command says which extra to install and exits with 1,
and it exits with 1 as well when the session cannot start, such as when the
port is in use.

::: redsun.examples.ExampleApp
    options:
      show_root_heading: true

::: redsun.examples.example_config
    options:
      show_root_heading: true

## Exit codes

| Code | When |
| --- | --- |
| 0 | the help or the version was printed, the example's window was closed, or the served example was stopped with Ctrl+C |
| 1 | the example could not start, or the extra it needs is not installed |
| 2 | an option or a style the command does not know, `--web` without `--example`, or `--web` with a style |
