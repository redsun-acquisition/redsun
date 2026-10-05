---
icon: lucide/scroll-text
---

# How to configure logging

`redsun` logs to one logger, `redsun`. By default it is at `INFO` and writes to
`sys.stdout`, with a formatter naming the component each record came from:

```text
[29-08-26|14:02:46][INFO][MyMotor -> stage]: Connected
[29-08-26|14:02:46][DEBUG][MyMotor -> stage]: setpoint=1.5 (motor.py:88)
```

[Log files](../reference/log-files.md) describes the shape of a record.

## Set the level for a session

Pass `log_level` to the session. It takes a `logging` constant or a level
name, as [`logging.Logger.setLevel`][logging.Logger.setLevel] does:

```python
import logging

from redsun.qt import QtSession


class MyApp(QtSession):
    config = "session.yaml"


app = MyApp(log_level=logging.DEBUG)
```

`Session.from_config` takes the same keyword:

```python
app = Session.from_config("session.yaml", log_level=logging.DEBUG)
```

Without it the logger keeps its level, `INFO` unless something changed it.

!!! note

    The level is a keyword, not a configuration file key: how much to report is
    usually decided per run, not per session.

## Set the level anywhere else

[`set_level`][redsun.log.set_level] sets the logger's level directly, for a
script or notebook without a session:

```python
from redsun.log import set_level

set_level("debug")
```

Names are case-insensitive, so a command-line flag's value works as is. An
unknown name raises `ValueError`.

## Find a session's log file

A session also writes a run's records to a file, opened when the build reads
the configuration and closed by `shutdown()`, and each launched service to a
file of its own. [Log files](../reference/log-files.md) says where they are,
what they are called and how long they are kept.

[`session_log`][redsun.log.session_log] returns the handler writing the current
run, and `session_log("camera_ioc")` the one writing that service's file. A
handler's `files` property lists its files with the oldest records first.

## Log from a service

A service's output is logged under `redsun.service.<service>`. A line that is a
JSON log record keeps its level, time and traceback, under
`redsun.service.<service>.<its logger>`; any other line, such as a `print`, is
logged at `DEBUG`. Two JSON layouts are read.

A Python service calls
[`configure_logging`][redsun.services.configure_logging] once, at startup:

```python
from redsun.services import configure_logging

configure_logging()
```

Its records of `logging`, and of `loguru` when it is installed, then reach the
session at the level the session records at, each keeping its level, time,
logger name and traceback. Started outside a session, the service logs at
`INFO`.

A service not written in Python writes one JSON object per line. Either the
layout of `loguru` with `serialize=True`, or an object with the fields `name`,
`levelno`, `created`, `msg` and `exc_text` of a `logging.LogRecord`.

A service's records follow its logger's level, so hiding its `DEBUG` output
is
`logging.getLogger("redsun.service.camera_ioc").setLevel(logging.INFO)`.

## Show the logs in the application

[`LogView`][redsun.view.qt.builtins.LogView] is a built-in Qt view of the
session's records. Name it under `views` in the session file:

```yaml
views:
  logs:
    plugin_name: redsun
    plugin_id: logs
```

![The log view at the bottom of a window, showing the records of a session as
it builds](images/log-view.png)

It sits at the bottom of the main window and shows every record of the
session, including those from the build, coloured by level. Application records
are on the **Application** tab. A **Services** tab appears once a service logs
something, with a selector for one service or all. The view keeps the latest
10 000 application records and 2 000 per service, so a noisy service never
pushes application records out. Its controls:

| Control | What it does |
| --- | --- |
| `Level` | shows only records at or above the chosen level, on both tabs; lowering it again brings hidden records back |
| `Save logs...` | writes the records of the tab shown to a file you choose, whatever level is shown: the application's, the selected service's, or every service's. It copies the session's log files, so records the view no longer holds are saved too |
| `Clear log window` | empties the console of the tab shown; the records stay available to `Level` and `Save logs...` |
| `Open log folder` | opens the folder holding the session's log files in the system's file browser |

Without session log files, as outside a session, `Save logs...` writes the
records held in memory and `Open log folder` is disabled.

??? example "The session of the picture"

    A session written in Python declares the view as any other:

    ```{.python}
    --8<-- "docs/examples/log_view.py:session"
    ```

## Send records somewhere else as well

[`add_handler`][redsun.log.add_handler] adds a destination beside the existing
ones, and [`remove_handler`][redsun.log.remove_handler] removes it:

```python
import logging

from redsun.log import add_handler, remove_handler

to_file = logging.FileHandler("session.log")
add_handler(to_file)
...
remove_handler(to_file)
```

A handler without a formatter gets the one stdout uses, so records read the
same everywhere. Set a formatter first to keep your own:

```python
to_file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
add_handler(to_file)
```

A handler's own level can make a destination quieter than the logger, never
louder: the logger's level decides which records exist. To write everything to
a file while the console stays at `INFO`, lower the logger and raise the
console handler.

## Log from your own component

Inherit [`Loggable`][redsun.log.Loggable] and use `self.logger`, an adapter on
the `redsun` logger that fills in the class and name shown in the output:

```python
from redsun.log import Loggable


class MyController(Loggable):
    def __init__(self, name: str) -> None:
        self.name = name
        self.logger.info("Initialized")
```

The name shown is the component's `name` attribute, so a message says which
instance wrote it:

```text
[29-08-26|14:02:46][INFO][MyController -> motor_ctrl]: Initialized
```

A class without a `name`, or with an empty or `None` one, logs with the class
alone in the brackets:

```text
[29-08-26|14:02:46][INFO][MyController]: Initialized
```

## Keep redsun out of your own logging

The `redsun` logger propagates, so a root logger handler also receives
`redsun`'s records. To keep them out, raise `redsun`'s level or stop
propagation:

```python
import logging

logging.getLogger("redsun").propagate = False
```

In a session, `redsun` never touches the root logger or any logger outside
`redsun`. `configure_logging` does, since it sets up the whole logging of a
service process.
