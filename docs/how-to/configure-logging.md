# Configure logging

`redsun` logs to one logger, `redsun`. By default it is at `INFO` and writes to
`sys.stdout`, with a formatter naming the component each record came from:

```text
[29-08-26|14:02:46][INFO][MyMotor -> stage]: Connected
[29-08-26|14:02:46][DEBUG][MyMotor -> stage]: setpoint=1.5 (motor.py:88)
```

Each record starts with the timestamp and level. What follows depends on what
wrote it:

| Written by | Shape |
| --- | --- |
| A [`Loggable`][redsun.log.Loggable] declaring a `name` | `[Class -> name]` |
| A `Loggable` declaring none, or an empty one | `[Class]` |
| `logging.getLogger("redsun")` directly | neither, just the message |

A record below `INFO` also shows the file and line it came from.

## Set the level for a session

Pass `log_level` to the container. It takes a `logging` constant or a level
name, as [`logging.Logger.setLevel`][logging.Logger.setLevel] does:

```python
import logging

from redsun.qt import QtAppContainer


class MyApp(QtAppContainer, config="session.yaml"): ...


app = MyApp(log_level=logging.DEBUG)
```

`AppContainer.from_config` takes the same keyword and passes it on:

```python
app = AppContainer.from_config("session.yaml", log_level=logging.DEBUG)
```

Without it the logger keeps its level, `INFO` unless something changed it.

!!! note

    The level is a keyword, not a configuration file key: how much to report is
    usually decided per run, not per session.

## Set the level anywhere else

[`set_level`][redsun.log.set_level] sets the logger's level directly, for a
script or notebook without a container:

```python
from redsun.log import set_level

set_level("debug")
```

Names are case-insensitive, so a command-line flag's value works as is. An
unknown name raises `ValueError`.

## Find a session's log file

A container also writes a run's records to a file, opened when the container
is constructed and closed by `shutdown()`. It sits under `logs/app` in the
user's data directory, as `platformdirs` reports it, the same root the
session's data goes under, in a folder named after the session:

| Platform | Folder |
| --- | --- |
| Windows | `%LOCALAPPDATA%\redsun\logs\app\<session>\` |
| macOS | `~/Library/Application Support/redsun/logs/app/<session>/` |
| Linux | `~/.local/share/redsun/logs/app/<session>/` |

Each run has its own file, named after its start time and process id, such as
`2026-09-13T14-02-46_8120.log`. At 10 MB a file rotates to `.log.1`, `.log.2`
and so on, keeping 5 older files. Starting a run deletes the files of all but
the session's 20 most recent runs.

Each launched service writes its own file under `logs/services/<session>/`,
named after the run and the service, such as
`2026-09-13T14-02-46_8120.camera_ioc.log`, rotated the same way and deleted
with the run's application file. The application's file holds no service
records, so a service logging heavily rotates only its own file. The file is
created when the service first logs something.

[`session_log`][redsun.log.session_log] returns the handler writing the current
run, and `session_log("camera_ioc")` the one writing that service's file. A
handler's `files` property lists its files with the oldest records first.

## Log from a service

A service's output is logged under `redsun.service.<service>`. A line that is a
JSON log record keeps its level, time and traceback, under
`redsun.service.<service>.<its logger>`; any other line, such as a `print`, is
logged at `DEBUG`. Two JSON layouts are read.

A service using `logging` adds a handler writing one JSON object per record to
standard output:

```python
import json
import logging
import sys


class JsonLines(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        traceback = self.formatException(record.exc_info) if record.exc_info else None
        return json.dumps(
            {
                "name": record.name,
                "levelno": record.levelno,
                "created": record.created,
                "msg": record.getMessage(),
                "exc_text": traceback,
            }
        )


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonLines())
logging.getLogger().addHandler(handler)
```

A service using `loguru` replaces its console sink with a serializing one:

```python
import sys

from loguru import logger

logger.remove()
logger.add(sys.stdout, serialize=True, level="INFO")
```

A service's records follow its logger's level, so hiding its `DEBUG` output
is
`logging.getLogger("redsun.service.camera_ioc").setLevel(logging.INFO)`.

## Show the logs in the application

[`LogView`][redsun.view.qt.builtins.LogView] is a built-in Qt view of the
session's records. Declare it under `views` like any other component:

```yaml
views:
  logs:
    plugin_name: redsun
    plugin_id: logs
```

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

Without session log files, as outside a container, `Save logs...` writes the
records held in memory and `Open log folder` is disabled.

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
from redsun.presenter import Presenter


class MyController(Presenter, Loggable):
    def __init__(self, name: str, devices: dict[str, Device]) -> None:
        super().__init__(name, devices)
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

`redsun` never touches the root logger or any logger outside `redsun`.
