---
icon: lucide/ban
---

# Limitations

Some things can't change once a session is built. This page lists them and
says what to do instead. For the parts `redsun` leaves to you, see
[Why redsun exists](statement.md#what-redsun-leaves-to-you).

## Can I add a value after startup?

No. Every [shared value](glossary.md#shared-value) reaches the session before
it starts running, in one of three ways: from a component, from a method
marked with [`provides`][redsun.provides], or from a plugin's provider. You
can't hand the session a new value later.

If something fills up over time, share a single object that changes, and let
the other components read it as it changes.

## Can a shared value be optional?

No. The session decides what exists by reading types before it builds, and
`Roi | None` is a type of its own: the session reports it as a value no
component asks for, even when one asks for `Roi | None`. The value still
arrives while it is a `Roi`, but when the method returns `None`, a component
asking for `Roi` fails its `setup`:

```python
@provides
def roi(self) -> Roi | None:  # does not do what it looks like
    return self._roi if self.camera.has_roi else None
```

Always share a value, and let the value say it's empty:

```python
@provides
def roi(self) -> Roi:
    return self._roi if self.camera.has_roi else Roi.empty()
```

Whether the value exists at all then depends only on whether the component
that shares it is in the session.

## Can two components share a type?

No. A type names one value, so two components sharing `Readings` is an error:

```text
TypeError: 'plot_b' and 'plot_a' both share 'Readings'.
A shared type identifies one value; give them distinct types.
```

Give each value its own type.

## Can I import parameter types under `if TYPE_CHECKING:`?

Not the types the session reads to decide what to pass: it reads them while
the program runs, when a type imported only under `if TYPE_CHECKING:`, a
block only type checkers read, doesn't exist. What happens depends on where
the type is used:

```d2 title="A type imported only for type checkers"
...@diagrams/style
direction: down
type: "a type imported\nunder if TYPE_CHECKING" {class: step}
where: "where is it used?" {shape: diamond; class: step}
component: "component left out,\nerror logged" {
  class: failed
  tooltip: The session logs a TypeError naming the type, and builds the rest.
}
stops: "build stops\nwith a NameError" {class: failed}
works: "works as usual" {class: step}
type -> where
where -> component: "constructor or setup\nof a component"
where -> stops: "return type of a provides\nmethod, or the session\nclass body"
where -> works: "anywhere else"
```

A component left out shows in the log like this:

```text
Failed to build presenter 'motor_ctrl': cannot read the constructor of
MotorPresenter: 'Calibration' is not available at runtime. A type a component
is injected by must be imported outside 'if TYPE_CHECKING', because the graph
evaluates the annotation.
```

Either way, import those types with a normal import.

## Can I run two frontends?

Not in one process. A `QtSession` owns the `QApplication`, and Qt allows only
one per process. Two sessions in one process also need different names,
because each registers an application under its own name.

## What happens when a service crashes?

The session logs it and emits a signal, but nothing restarts the service, so
it stays down:

```d2 title="A launched service that stops on its own"
...@diagrams/style
direction: right
exit: "the service\nexits" {class: failed}
log: "ERROR in the log:\nexit code and\nlast lines of output" {class: step}
signal: "sig_exited\nname and code" {
  class: step
  tooltip: Emitted from the thread that reads the service's output.
}
down: "the service\nstays down" {
  class: step
  tooltip: Reads and writes on its devices raise TimeoutError after ten seconds, until the service is back.
}
exit -> log -> signal -> down
```

See [Services](services.md#unexpected-exits).
