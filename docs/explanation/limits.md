---
icon: lucide/ban
---

# What a session does not do

What a session does not do, and what to do instead.

## A value cannot be added while the session runs

Values enter a session in three ways, all before it starts running: a
component, a method marked with [`provides`][redsun.provides], or a plugin's
provider. There is no way to hand the session a new value later.

If something fills up over time, share an object that changes, once, and let
others read it as it changes.

## A shared value cannot be optional

The session decides what exists by reading types, before anything is built. A
`provides` method returning `Roi | None` shares a value of type `Roi | None`,
not `Roi`, so a component asking for `Roi | None` never receives it:

```python
@provides
def roi(self) -> Roi | None:  # does not do what it looks like
    return self._roi if self.camera.has_roi else None
```

Always share a value, and let the value say it is empty:

```python
@provides
def roi(self) -> Roi:
    return self._roi if self.camera.has_roi else Roi.empty()
```

Whether a value exists at all is decided by whether the component sharing it
is in the session.

## Two components cannot share one type

A type names one value, so two components sharing `Readings` is an error:

```text
TypeError: 'plot_b' and 'plot_a' both share 'Readings'.
A shared type identifies one value; give them distinct types.
```

Give each value its own type.

## A type used for lookup must be imported normally

The session reads a constructor's annotations while the program runs, to know
what to pass. A type imported only under `if TYPE_CHECKING:` is not there when
it looks:

```text
TypeError: cannot read the constructor of MotorPresenter: 'Calibration' is not
available at runtime.
```

Import such types normally. This applies to the constructor and `setup` of a
component, the return type of a `provides` method, and the session class body.
Everywhere else, `TYPE_CHECKING` imports work as usual.

## One frontend per process

A `QtSession` owns the `QApplication`, and Qt allows one per process. Two
sessions in one process must also have different names, since each registers
an application under its name.

## Nothing restarts a crashed service

A launched service that exits is logged and reported with a signal, and stays
down. See [Services](services.md#a-service-exiting).
