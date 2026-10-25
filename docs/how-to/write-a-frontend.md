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
so two spellings of one key are seen as the same. A binding that
[`resolve_shortcuts`][redsun.Session.resolve_shortcuts] returns with a
`when` function acts only while that function returns true, so ask it again
each time the focus moves and leave the key press to the focused widget
while it returns false. A binding whose `repeat` is false runs its command
once per press, so let a held key repeat only the bindings that ask for it.
A binding's `run` can be a coroutine method. Start it without waiting, so
the key press returns at once. A presenter's coroutine methods always
reach you. A view's reach you only when your frontend sets `view_coroutines`
to true, which says its views may be used from the loop the coroutine runs
on; otherwise the session leaves those keys out.
A frontend that lets the user change keys calls
[`set_shortcuts`][redsun.Session.set_shortcuts] or
[`reset_shortcuts`][redsun.Session.reset_shortcuts], then binds what
`resolve_shortcuts` returns again.

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

## Call hook points

A [hook point](../explanation/glossary.md#hook-point) is a moment of your
toolkit at which a user's provider may act, such as "the application
exists". List yours in `hook_points`, each with the protocol a provider
must satisfy. A point takes one provider, or any number when you wrap its
protocol in [`Many`][redsun.Many]:

```python
from typing import ClassVar, Protocol, runtime_checkable

from redsun import Many, Session


@runtime_checkable
class ConfiguresScreen(Protocol):
    def configure_screen(self, screen: Screen) -> None: ...


class ConsoleSession(Session):
    hook_points: ClassVar = {"configure_screen": Many(ConfiguresScreen)}

    def start_runtime(self) -> None:
        super().start_runtime()
        screen = Screen()
        self.call_hooks(
            "configure_screen", lambda provider: provider.configure_screen(screen)
        )
```

[`call_hooks`][redsun.Session.call_hooks] calls every provider at the point,
in order. A provider that raises is logged and skipped, and the next one is
called. Where you use what a provider returns, read
[`hooks`][redsun.Session.hooks] yourself, and hand a provider that raised to
[`skip_hook`][redsun.Session.skip_hook].
[Hook points](../reference/hook-points.md) lists the rules a session keeps
for its providers.

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
