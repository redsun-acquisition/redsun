---
icon: lucide/monitor-cog
---

# How to write a frontend

To show a session with something other than Qt, you define the placements a
view can ask for, a `Frontend` that lists them, and a session class that puts
the views in place and runs the loop that delivers their calls.
[How a frontend shows a session on screen](../explanation/frontends.md)
explains what a frontend is responsible for.

## Prerequisites

You need the [toolkit](../explanation/glossary.md#toolkit) your frontend
shows views with. The example below prints one line of text for each view to
the terminal, so it needs nothing beyond `redsun`. The blocks below are parts
of one script, and the whole script is at the end.

## Define the placements

A placement is a frozen dataclass subclassing [`Placement`][redsun.Placement].
Define one for each place your toolkit can put a view, plus a base class that
the views of that place must be a subclass of:

```{.python}
--8<-- "docs/examples/console_frontend.py:placement"
```

## Define the frontend

Subclass [`Frontend`][redsun.Frontend]. `requires` maps each placement to the
class a view asking for it must be, and the session refuses a view that asks
for another placement, or is of another class, before building it. `thread_of`
names the thread the slots of a view run on when the slot doesn't say:

```{.python}
--8<-- "docs/examples/console_frontend.py:frontend"
```

Most toolkits allow their objects to be used from one thread only, so views
run on `"main"`. If `thread_of` returns `None`, the slot runs on the thread
that sent the signal.

To refuse a view class for another reason, such as a constructor your
toolkit can't call, override
[`check_view`][redsun.Frontend.check_view] and raise `TypeError`.

If your frontend binds keyboard shortcuts, override `key_problems`, to refuse
a key your toolkit can't bind, and `canonical_key`, to write each key one way
so two spellings of one key are seen as the same.

## Define the session

Subclass [`Session`][redsun.Session], set `frontend`, and fill `present`,
which runs once every view is built and linked:

```{.python}
--8<-- "docs/examples/console_frontend.py:session"
```

`run` builds the session, then loops until the user stops it. Each turn it
calls `psygnal.emit_queued()`, which delivers the calls held for the main
thread, and then shows the views. If your toolkit has an event loop of its
own, call `psygnal.emit_queued()` from a timer of that loop instead.

- To pass more arguments to every view's constructor, as `QtSession` passes
  `parent`, override the property
  [`view_arguments`][redsun.Session.view_arguments].
- To make toolkit objects before any component exists, such as the
  application object of the toolkit, override `start_runtime` and call
  `super().start_runtime()` first, which sets the backend that coroutine slots
  run on.

## Write a view for it

A view subclasses the base class of its placement and names the placement:

```{.python}
--8<-- "docs/examples/console_frontend.py:view"
```

```{.python}
--8<-- "docs/examples/console_frontend.py:app"
```

## Support window layouts

A frontend that can arrange its window shows the layout a session declares.
List the regions of your window in `regions`, each with how a view the
layout leaves out joins it, and say which region each of your placements
asks for in `region_of`:

```python
from collections.abc import Mapping
from typing import ClassVar

from redsun import Column, Frontend, Placement, Row, Tabs


class ConsoleFrontend(Frontend):
    regions: ClassVar[Mapping[str, type[Row] | type[Column] | type[Tabs]]] = {
        "screen": Column,
    }
    hides: ClassVar[bool] = False

    @classmethod
    def region_of(cls, placement: Placement) -> tuple[str, str | None] | None:
        return ("screen", None) if isinstance(placement, Line) else None
```

`Line` is the placement your frontend defines. The session refuses a layout
that names a region you don't list, or hides a view when `hides` is false.

In `present`, call `self.resolve_layout()` and build the window from what it
returns: the declared layout, with every other view added where its
placement asks. If your window saves how the user arranged it, save
`fingerprint()` of that layout beside it, and restore the arrangement only
while the fingerprint matches.

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
