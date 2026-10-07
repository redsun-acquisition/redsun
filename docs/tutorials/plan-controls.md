---
icon: lucide/list-checks
---

# Building controls for a plan

In this tutorial you write a plan, and the window gains the controls to run
it: a list of the plans to choose from and, for the plan you choose, a list
of stages, an input for each parameter and a **Run** button. You don't build
those controls yourself, because `redsun` builds them from the plan as a
[plan widget](../explanation/glossary.md#plan-widget). It continues from
[Describing a device with a protocol](device-protocols.md).

You write three components. The first offers a
[plan](../explanation/glossary.md#plan), a recipe for an acquisition. The
second runs plans on a [`RunEngine`](../explanation/glossary.md#runengine),
and the third shows the plan widget of the plan you choose. The second and
third never name the first: they ask the session which components offer
plans, and the session answers.

## Before you start

!!! note "What you need"

    The project folder as you left it, and nothing else.

Open `first_session.py`, and add these imports below the ones it has:

```python
from collections.abc import Mapping
from typing import Any

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from qtpy.QtWidgets import QComboBox, QStackedWidget, QVBoxLayout

from redsun import CallbackType, HasPlans, PlanEntry
from redsun.engine import RunEngine
from redsun.presenter.plan_spec import (
    PlanSpec,
    collect_arguments,
    create_plan_spec,
    resolve_arguments,
)
from redsun.view.qt.utils import PlanWidget, create_plan_widget
```

Nothing you've written so far changes in this tutorial.

## 1. Offer a plan

Add a presenter below `StageView`. It holds a plan called `walk`, and offers
it to the rest of the session:

```{.python}
--8<-- "docs/tutorials/plan_controls.py:stage_plans"
```

`walk` reads where a stage is with [`bps.rd`][bluesky.plan_stubs.rd], moves it
one step further with [`bps.mv`][bluesky.plan_stubs.mv], and repeats. Notice
that it isn't `async`, because the [`RunEngine`][redsun.engine.RunEngine]
does the waiting. It takes its stage as a `HasPosition`, so it works with any
stage of the session.

A component offers plans through `plan_map`, which returns each plan under
its name as a [`PlanEntry`][redsun.PlanEntry]. Any component with that method
satisfies the protocol [`HasPlans`][redsun.HasPlans].

## 2. Run the plans

Add a second presenter below `StagePlans`. It has a `RunEngine`, which it uses
to run the plans the session holds:

```{.python}
--8<-- "docs/tutorials/plan_controls.py:plan_ctrl"
```

`setup` runs once every component exists, and the session fills in its
parameters. `providers` asks for every component that satisfies `HasPlans`,
so `PlanPresenter` receives `StagePlans` without naming it. `callbacks` asks
for the components that follow a plan while it runs, and the next tutorial
adds one. [`create_plan_spec`][redsun.presenter.plan_spec.create_plan_spec]
then describes each plan from its signature.

`run` receives the name of a plan and the values the user chose. Since the
user picks a stage by its name,
[`resolve_arguments`][redsun.presenter.plan_spec.resolve_arguments] puts the
device in place of the name, and
[`collect_arguments`][redsun.presenter.plan_spec.collect_arguments] orders the
values the way the plan takes them. The engine starts the plan without
waiting for it to end, and the presenter sends `sig_finished` once it has.

## 3. Build the controls

Add a view below `PlanPresenter`. It asks the session for the same
components, and builds a plan widget for each plan they offer. It holds all
the widgets, and shows the one for the plan chosen in its list:

```{.python}
--8<-- "docs/tutorials/plan_controls.py:plan_view"
```

[`create_plan_widget`][redsun.view.qt.utils.create_plan_widget] builds the
plan widget from the description of the plan. The view disables itself while
a plan runs, and enables itself again when the presenter says the plan has
finished.

`redsun` doesn't ship these two components, because each application decides
how its plans are run and shown. You write them once.

## 4. Add them to the session

Add the highlighted lines:

```{.python hl_lines="6 7 9 15 16"}
--8<-- "docs/tutorials/plan_controls.py:session"
```

No link joins `stage_plans` to the other two, because the session passes it
to them in `setup`.

Run the script:

```bash
uv run first_session.py
```

```text
Session built: 2/2 devices, 3/3 presenters, 2/2 views
```

![The window of the session: the rows of the two stages on the left, and on
the right a list of plans that shows walk, above the plan widget of walk: a
list of stages, an input for steps, an input for size and a Run
button](images/plan-controls.png)

The view on the right starts with the list of the plans, which holds only
`walk` for now. Below it is the plan widget of `walk`: a list with the two
stages, an input for `steps` and one for `size` with the defaults you wrote,
and a **Run** button.

The list of stages holds the devices that satisfy `HasPosition`. Python
checks that while the program runs, which is what `runtime_checkable`
allowed.

## 5. Run the plan

Leave `stage` selected in the list of stages and press **Run**. The view of
the plans greys out and the position of `stage` counts up on the left. Then
the view comes back, and the stage has moved five steps of one millimetre,
to `5.0`.

`walk` moves by its own `size`, since the `step` in `session.yaml` only
applies to the buttons of the stages.

If a plan fails, the terminal tells you why, and the view comes back.

## 6. Change the parameters

Choose `fast_stage` in the list of stages, set `steps` to `10` and `size` to
`0.5`, and press **Run** again. This time the position of `fast_stage` counts
up, by half a millimetre at a time.

You didn't write any code for the list or the inputs, because they follow
the signature of `walk`.

??? example "The whole script"

    ```{.python}
    --8<-- "docs/tutorials/plan_controls.py"
    ```

## What you built

You built controls that run a plan on the stage you choose, with the number
and size of steps you type in. While the plan runs, the window shows the
stage moving, and only the view of the plans is greyed out. Any component
that offers a plan adds an entry to the list of the plans, with no change to
the presenter or the view you wrote here.

## Next steps

- [Acquiring images](acquire-images.md) is the next tutorial, where you add a
  camera and a component that offers a plan to acquire with it.
- [Questions](../explanation/questions.md) explains how a component asks the
  session what it holds.
- [How presenters run plans](../explanation/plans.md) covers plans that run
  until they are stopped, and actions the user takes while they run.
- [How the Qt widgets of redsun work](../explanation/qt-widgets.md) lists what a
  plan widget can hold.
