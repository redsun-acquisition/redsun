---
icon: lucide/link
---

# How to offer a pairing

A presenter and a view written for each other can connect with one line in a
session file, `pairs: - [view, presenter]`, instead of one line per link. This
page is for the author of the two components.
[ADR 23](../explanation/decisions/0023-pairing-two-components.md) explains
the design.

## Name the signal on each slot

Give each slot the attribute name of the signal of the other component that
should reach it, with `signal` on [`slot`][redsun.slot]:

```python
from psygnal import Signal
from qtpy.QtWidgets import QWidget

from redsun import slot


class MyController:
    sig_moved = Signal(str, float)

    @slot(signal="sig_requested")
    def move(self, axis: str, amount: float) -> None: ...


class MyView(QWidget):
    sig_requested = Signal(str, float)

    @slot(signal="sig_moved")
    def update_position(self, axis: str, position: float) -> None: ...
```

A slot reached by several signals takes a tuple,
`@slot(signal=("sig_moved", "sig_homed"))`. A slot without `signal` stays out
of a pairing, but a link you list in the session still connects it.

## Pair them in a session

In a session file:

```yaml
pairs:
  - [my_view, my_ctrl]
```

In a session class, yield what [`links_between`][redsun.links_between]
returns:

```python
from collections.abc import Iterator

from redsun import Link, links_between


def wire(self) -> Iterator[Link]:
    yield from links_between(self.my_view, self.my_ctrl)
```

Each signal of one component reaches each slot of the other naming it, both
ways. Only [`psygnal`](../explanation/glossary.md#psygnal) signals are matched,
so link a device signal on its own.

## What the session checks

- A pairing of two built components that matches nothing raises
  `WiringError` naming both.
- A pairing naming one component twice is refused when the file is read.
- A pairing naming a component that failed to build is skipped with a
  warning, as a link to it is.
- A link already made by `wire`, by `wiring` or by another pairing is not
  made again, so a session can list a link by hand and pair the two.
- A slot needing more arguments than its signal sends raises `WiringError`
  when the session connects it. Argument types are not compared.

## Name a signal for what it does

A pairing connects every name that matches, in both directions, so a component
paired with one it wasn't written for connects whatever happens to share a
name. Give a signal a name that says what it does (`sig_stop_device`, not
`sig_stop`, for a signal stopping one device), pair components written for
each other, and link the rest one by one.
