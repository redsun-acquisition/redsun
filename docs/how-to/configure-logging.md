# Configure logging

Everything redsun writes goes to one logger, named `redsun`. Out of the box it
is set to `INFO` and writes to `sys.stdout` through a formatter that adds the
component a record came from:

```text
[29-08-26|14:02:46][INFO][MyMotor -> stage]: Connected
[29-08-26|14:02:46][DEBUG][MyMotor -> stage]: setpoint=1.5 (motor.py:88)
```

Every record opens with the timestamp and the level. What follows depends on
what wrote it:

| Written by | Shape |
| --- | --- |
| A [`Loggable`][redsun.log.Loggable] declaring a `name` | `[Class -> name]` |
| A `Loggable` declaring none, or an empty one | `[Class]` |
| `logging.getLogger("redsun")` directly | neither, just the message |

A record below `INFO` carries the file and line it came from as well, since
that is where it is useful.

## Set the level for a session

Pass `log_level` when you build the container. It takes a `logging` constant or
a level name, exactly as
[`logging.Logger.setLevel`][logging.Logger.setLevel] does:

```python
import logging

from redsun.qt import QtAppContainer


class MyApp(QtAppContainer, config="session.yaml"): ...


app = MyApp(log_level=logging.DEBUG)
```

`AppContainer.from_config` takes the same keyword and hands it to the container
it builds:

```python
app = AppContainer.from_config("session.yaml", log_level=logging.DEBUG)
```

Leave it out and the logger keeps whatever level it has, which is `INFO` unless
something already changed it.

!!! note

    The level is a keyword rather than a key in the configuration file. It says
    how much a particular run should report, which is usually a decision about
    the run rather than about the session.

## Set the level anywhere else

[`set_level`][redsun.log.set_level] reaches the logger directly, for a script or
a notebook that never builds a container:

```python
from redsun.log import set_level

set_level("debug")
```

A name is matched without regard to case, so a value taken straight from a
command-line flag works. One that names no level raises `ValueError`.

## Send records somewhere else as well

[`add_handler`][redsun.log.add_handler] adds a destination without disturbing
the one already there, and [`remove_handler`][redsun.log.remove_handler] takes
it away again:

```python
import logging

from redsun.log import add_handler, remove_handler

to_file = logging.FileHandler("session.log")
add_handler(to_file)
...
remove_handler(to_file)
```

A handler carrying no formatter of its own is given the one stdout writes
through, so a record reads the same wherever it lands. Set a formatter on the
handler first to keep your own:

```python
to_file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
add_handler(to_file)
```

Handlers have levels of their own, so a destination can be quieter than the
logger but never louder: the logger's level decides which records exist at all.
To write everything to a file while keeping the console at `INFO`, lower the
logger and raise the console handler.

## Log from your own component

Inherit [`Loggable`][redsun.log.Loggable] and use `self.logger`. It is an
adapter over the same `redsun` logger, and it fills in the class and name shown
in the output:

```python
from redsun.log import Loggable
from redsun.presenter import Presenter


class MyController(Presenter, Loggable):
    def __init__(self, name: str, devices: dict[str, Device]) -> None:
        super().__init__(name, devices)
        self.logger.info("Initialized")
```

The name in the output is the component's own `name` attribute, so a message
says which of several instances wrote it without you passing the name in:

```text
[29-08-26|14:02:46][INFO][MyController -> motor_ctrl]: Initialized
```

A class that declares no `name` still logs, with the class alone in the
brackets. So does one whose `name` is empty or `None`, since the field is
dropped when there is nothing to show:

```text
[29-08-26|14:02:46][INFO][MyController]: Initialized
```

## Keep redsun out of your own logging

The `redsun` logger propagates, so a handler on the root logger sees redsun's
records alongside your application's. If you configure the root logger yourself
and do not want them there, either raise redsun's level or stop the propagation:

```python
import logging

logging.getLogger("redsun").propagate = False
```

Nothing redsun does touches the root logger or any logger outside `redsun`, so
configuring your own logging does not have to work around it.
