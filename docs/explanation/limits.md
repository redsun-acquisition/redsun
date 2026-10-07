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

No. The session decides what exists by reading types, before it builds
anything. A `provides` method returning `Roi | None` shares a value of type
`Roi | None`, not `Roi`. A component asking for `Roi | None` looks for a
`Roi`, so it never receives the value:

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

## How must I import a lookup type?

Import a type the session looks up normally, not under `if TYPE_CHECKING:`.
The session reads a constructor's annotations while the program runs, to know
what to pass it, and a type imported only under `if TYPE_CHECKING:`, a block
that only type checkers read, isn't there when the session looks:

```text
TypeError: cannot read the constructor of MotorPresenter: 'Calibration' is not
available at runtime.
```

This applies to the constructor and `setup` of a component, the return type
of a `provides` method, and the session class body. Everywhere else,
`TYPE_CHECKING` imports work as usual.

## Can I run two frontends?

Not in one process. A `QtSession` owns the `QApplication`, and Qt allows only
one per process. Two sessions in one process also need different names,
because each registers an application under its own name.

## What happens when a service crashes?

The session logs it and emits a signal, but nothing restarts the service, so
it stays down. See [Services](services.md#unexpected-exits).
