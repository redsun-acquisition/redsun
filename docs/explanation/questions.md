---
icon: lucide/circle-help
---

# How a component asks the session what it holds

A component usually asks for one thing by its type. Sometimes it needs an
answer instead, such as "which components can be reset?", which depends on
what the session file puts in the session. It asks in
[`setup`](glossary.md#setup), with a [protocol](glossary.md#protocol)
describing what it looks for.

## Asking with an annotation

How you annotate the parameter says what you're asking for:

| annotation | what you get |
| --- | --- |
| `P` | the one component, or shared value, that satisfies `P` |
| `P \| None = None` | that one, or `None` if nothing does |
| `Mapping[str, P]` | every component satisfying `P`, by name |

```python
from collections.abc import Mapping
from typing import Protocol

from redsun import slot


class Resettable(Protocol):
    def reset(self) -> None: ...


class SessionPresenter:
    def __init__(self, name: str) -> None:
        self.name = name

    def setup(self, resettable: Mapping[str, Resettable]) -> None:
        self.resettable = resettable

    @slot
    def reset_all(self) -> None:
        for component in self.resettable.values():
            component.reset()
```

Whatever the session file puts in the session, `reset_all` resets all of it,
and nobody has to keep a list up to date.

[ADR 17](decisions/0017-questions-read-from-the-annotation.md) records why the
annotation carries the question.

## How a component matches

A component matches when it has every member the protocol lists and each
method accepts every call the protocol allows. Step through who answers and
who comes close:

```d2 title="Which components answer Mapping[str, Resettable]"
...@diagrams/style
direction: right
plot: "plot\nno reset" {class: step; width: 190; height: 70}
loose: "loose\nreset(hard)" {class: step; width: 190; height: 70}
detector: "detector\nreset(force=False)" {class: step; width: 190; height: 70}
motor: "motor\nreset()" {class: step; width: 190; height: 70}
asker: "SessionPresenter.setup\nresettable:\nMapping[str, Resettable]" {class: step; width: 240}
plot -> asker: {style.opacity: 0}
loose -> asker: {style.opacity: 0}
detector -> asker: {style.opacity: 0}
motor -> asker: {style.opacity: 0}
steps: {
  1: {
    motor.class: current
    detector: {
      class: current
      tooltip: "An extra parameter with a default still matches, because reset() can still be called."
    }
    (motor -> asker)[0].style.opacity: 1
    (detector -> asker)[0].style.opacity: 1
  }
  2: {
    loose: {
      class: failed
      tooltip: "A renamed parameter, or an extra one without a default, doesn't match. Session.rejected lists it with the reason."
    }
    plot: {
      class: done
      tooltip: "It has none of the protocol's members, so Session.rejected leaves it out too."
    }
  }
}
```

This is [structural subtyping](glossary.md#structural-subtyping): no
inheritance needed, and types aren't compared, which is a type checker's job.
The protocol needs no `runtime_checkable`, may list attributes, and may be
generic (`Reading[float]` is matched as `Reading`). When a component you
expected is missing, [`Session.satisfying`][redsun.Session.satisfying] shows
the answer and [`Session.rejected`][redsun.Session.rejected] says why:

```python
>>> session.satisfying(Resettable)
{'motor': <Motor>, 'detector': <Detector>}
>>> session.rejected(Resettable)
{'loose': ["reset(hard) cannot be called as reset(): missing a required argument: 'hard'"]}
```

`rejected` lists only components that have some of the protocol's members, so
the near misses are easy to find.

## Asking for exactly one

A parameter annotated with the protocol alone asks for the one component, or
shared value, that satisfies it:

```python
class RoiView(QWidget):
    def setup(self, camera: HasCamera) -> None:
        self.camera = camera
```

Use `P | None = None` when the component can do without:

```python
def setup(self, roi: HasRoi | None = None) -> None:
    self.roi = roi
```

What the component gets depends on how many things match:

| matches | `camera: HasCamera` | `roi: HasRoi \| None = None` |
| --- | --- | --- |
| one | that one | that one |
| none | the build stops, and the error names what came close | `None` |
| the only match failed to build | the component is reported as not set up, and runs without it | `None` |
| two or more | the build stops | the build stops |

When two or more match, the error says which:

```text
TypeError: 'roi' in its 'camera' parameter asks for the one object satisfying
'HasCamera', but 2 do, from 'camera', 'spare'. Narrow the protocol, or ask for
'Mapping[str, HasCamera]'.
```

A component never answers its own single question, but it does appear in its
own `Mapping[str, P]`, which describes the whole session the same way for
everyone. Leave yourself out with one line:

```python
others = {name: c for name, c in self.resettable.items() if name != self.name}
```

## Asking about devices

Devices never answer a question in `setup`. A device is asked about in a
constructor, with [`DevicesOf`][redsun.DevicesOf]:

```d2 title="Who answers which question, and where"
...@diagrams/style
direction: right
devices: "devices" {class: layer; width: 200}
components: "presenters\nand views" {class: layer; width: 200}
shared: "shared values" {class: step; width: 200}
constructor: "in a constructor\nDevicesOf[P]" {class: step; width: 220}
every: "in setup\nMapping[str, P]" {class: step; width: 220}
one: "in setup\nP or P | None" {class: step; width: 220}
devices -> constructor
components -> every
components -> one
shared -> one
```

```python
class MotorPresenter:
    def __init__(self, name: str, *, motors: DevicesOf[Movable]) -> None:
        self.name = name
        self.motors = motors
```

Devices exist before any presenter, so the constructor can ask. `DevicesOf`
works only as `Mapping[str, P]` in a constructor; for every device, ask for
[`DeviceMapping`][redsun.DeviceMapping].

## When not to ask

- To get one specific value, ask for it by its class instead.
- If components only need to hear when something happens, connect a signal
  to a slot in `wire` and skip the question.

!!! warning "A component can answer a question by accident"

    A component answers a question by what it has, whether it meant to or
    not, so any class with a `reset` method is `Resettable`. If that's not
    what you want, rename the method.
