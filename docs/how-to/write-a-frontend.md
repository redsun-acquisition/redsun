---
icon: lucide/monitor-cog
---

# How to write a frontend

Show a session with something other than Qt: define the placements a view can
ask for, a `Frontend` that lists them, and a session class that puts the
views in place and runs the loop that delivers their calls.
[How a frontend shows a session on screen](../explanation/frontends.md)
explains what a frontend is responsible for.

## Prerequisites

The toolkit the frontend shows views with. The example below prints one line
of text for each view to the terminal, so it needs nothing beyond `redsun`.
The blocks below are parts of one script; the whole script is at the end.

## Define the placements

A placement is a frozen dataclass subclassing
[`Placement`][redsun.Placement]. Define one for each place your toolkit can
put a view, and a base class the views of that place must be:

```{.python}
--8<-- "docs/examples/console_frontend.py:placement"
```

## Define the frontend

Subclass [`Frontend`][redsun.Frontend]. `requires` maps each placement to the
class a view asking for it must be; a view asking for another placement, or
of another class, is refused before it is built. `thread_of` names the
thread the slots of a view run on when the slot does not say:

```{.python}
--8<-- "docs/examples/console_frontend.py:frontend"
```

Most toolkits allow their objects to be used from one thread only, so views
run on `"main"`. Returning `None` runs a slot on the thread that sent the
signal.

To refuse a view class for another reason, such as a constructor your
toolkit cannot call, override
[`check_view`][redsun.Frontend.check_view] and raise `TypeError`.

## Define the session

Subclass [`Session`][redsun.Session], set `frontend`, and fill `present`,
which runs once every view is built and linked:

```{.python}
--8<-- "docs/examples/console_frontend.py:session"
```

`run` builds the session, then loops until the user stops it. Each turn it
calls `psygnal.emit_queued()`, which delivers the calls held for the main
thread, and then shows the views. A toolkit with an event loop of its own
calls `psygnal.emit_queued()` from a timer of that loop instead.

- To pass more arguments to every view's constructor, as `QtSession` passes
  `parent`, override the property
  [`view_arguments`][redsun.Session.view_arguments].
- To make toolkit objects before any component exists, such as the
  application object of the toolkit, override `start_runtime` and call the
  one it overrides first: that one sets the backend coroutine slots run on.

## Write a view for it

A view subclasses the base class of its placement and names the placement:

```{.python}
--8<-- "docs/examples/console_frontend.py:view"
```

```{.python}
--8<-- "docs/examples/console_frontend.py:app"
```

## Let a session file name it

Register the session class in the `redsun.frontends` entry point group of
your package:

```toml
[project.entry-points."redsun.frontends"]
console = "mylab.console:ConsoleSession"
```

A session file then names it with `frontend: console`.

## The example in full

??? example "The whole script"

    ```{.python}
    --8<-- "docs/examples/console_frontend.py"
    ```
