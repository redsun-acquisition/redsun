---
icon: lucide/sliders-horizontal
---

# How to change a device setting while a plan runs

A user changes a device setting from a view while the engine runs a plan. A
camera's region of interest is the usual case: applied halfway through a
point, one event stream carries frames of two shapes, and the store the
service writes no longer matches the `StreamResource` describing it. Any
setting a plan's readings depend on has the same problem.

[`Deferrals`][redsun.engine.Deferrals] applies such a change between two
messages of the plan instead: once the message under way completes, every
change queued by then runs before the next message is sent. The plan
contains nothing about it, so every plan gets the behaviour, and it is
neither suspended nor rewound. A change asked for during a plan's last
message runs before the plan returns, so whoever waits on the plan's result
finds it applied.

## Build one beside the engine

Whoever owns the [`RunEngine`][redsun.engine.RunEngine] builds the
`Deferrals` and [shares](../reference/glossary.md#shared-value) it:

```python
from redsun import provides
from redsun.engine import Deferrals, RunEngine


class AcquisitionPresenter:
    def __init__(self, name: str) -> None:
        self.name = name
        self.engine = RunEngine()
        self._deferrals = Deferrals(self.engine)

    @provides
    def deferrals(self) -> Deferrals:
        return self._deferrals
```

## Ask for it where the setting is written

A component writing a setting asks for `Deferrals` in `setup`, and hands the
write over as a coroutine function:

```python
from redsun import DevicesOf, slot
from redsun.engine import Deferrals


class DetectorPresenter:
    def __init__(self, name: str, *, detectors: DevicesOf[HasRoi]) -> None:
        self.name = name
        self.detectors = detectors

    def setup(self, deferrals: Deferrals) -> None:
        self._deferrals = deferrals

    @slot
    async def set(self, detector: str, value: str) -> None:
        signal = self.detectors[detector].roi

        async def apply() -> None:
            await signal.set(value)

        self._deferrals.request(apply)
```

`request` returns at once, with a future done once the change ran on the
engine's loop. While a plan runs, the change waits for the next message
boundary; while none runs, it is applied straight away. A thread may wait on
the future; a coroutine must not block on it.
Several changes asked for during one message are applied together, in the
order asked. A change that raises is logged under `redsun` and the ones after
it still run.

## What a plan sees

Nothing. `Deferrals` is a preprocessor on the engine, and it runs each queued
change as a `wait_for` inserted before the plan's next message. No message
runs twice: a `bluesky` suspension would rewind to the last checkpoint and
replay what came after it, which is why one is not used. A change waits as
long as the message under way takes, so a plan that sleeps or waits for a
long move delays it by that much.
