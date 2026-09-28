---
icon: lucide/list-checks
---

# Building controls for a plan

In this tutorial you write a plan, and the window gains the controls to run it:
a list of the plans to choose from, and for the plan chosen a list of stages,
an input for each parameter, and a **Run** button. `redsun` builds them from
the plan, as a [plan widget](../explanation/glossary.md#plan-widget). It
continues from [Describing a device with a protocol](device-protocols.md).

You will write three components: one that offers a
[plan](../explanation/glossary.md#plan), one that runs plans on a
[`RunEngine`](../explanation/glossary.md#runengine), and one that shows the
plan widget of the plan you choose. The last two never name the first. They ask
the session who offers plans, and the session answers.

## Before you start

!!! note "What you need"

    The project folder as you left it, and nothing else.

Open `first_session.py`, and add these imports to the ones it has:

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

Nothing you wrote so far changes in this tutorial.

## 1. Offer a plan

Add a presenter below `StageView`. It holds a plan, called `walk`, and offers
it:

```{.python}
--8<-- "docs/tutorials/plan_controls.py:stage_plans"
```

`walk` reads where a stage is with [`bps.rd`][bluesky.plan_stubs.rd], moves it
one step further with [`bps.mv`][bluesky.plan_stubs.mv], and repeats. Notice
that it is not `async`: the [`RunEngine`][redsun.engine.RunEngine] does the
waiting. It takes its stage as a `HasPosition`, so it works with any stage of
the session.

`plan_map` is how a component offers plans: it returns each one under its
name, as a [`PlanEntry`][redsun.PlanEntry]. A component with that method
satisfies the protocol [`HasPlans`][redsun.HasPlans].

## 2. Run the plans

Add a second presenter below `StagePlans`. It has a `RunEngine`, and runs the
plans the session holds:

```{.python}
--8<-- "docs/tutorials/plan_controls.py:plan_ctrl"
```

Look at `setup`. It runs once every component exists, and the session fills
its parameters:

- `providers` asks for every component that satisfies `HasPlans`, by name.
  `PlanPresenter` does not name `StagePlans`, and receives it.
- `callbacks` asks for the components that follow a plan while it runs. The
  session has none yet, and the next tutorial adds one.

[`create_plan_spec`][redsun.presenter.plan_spec.create_plan_spec] reads the
signature of a plan and describes it, as a
[`PlanSpec`][redsun.presenter.plan_spec.PlanSpec].

`run` takes the name of a plan and the values the user chose, and starts the
plan. It does not wait for the plan to end: `sig_finished` tells the view
when it is over.

## 3. Build the controls

Add a view below `PlanPresenter`. It asks the same question, and builds a
plan widget for each plan it receives. It holds them all, and shows the one
of the plan chosen in its list:

```{.python}
--8<-- "docs/tutorials/plan_controls.py:plan_view"
```

[`create_plan_widget`][redsun.view.qt.utils.create_plan_widget] builds the
plan widget from the description of the plan. The view disables itself while
a plan runs, and enables itself again when the presenter says the plan has
finished.

## 4. Add them to the session

Add the highlighted lines:

```{.python hl_lines="5 6 8 14 15"}
--8<-- "docs/tutorials/plan_controls.py:session"
```

No link joins `stage_plans` to the other two. The session passed it to them
in `setup`.

Run the script:

```bash
uv run first_session.py
```

```text
Container built: 2/2 devices, 3/3 presenters, 2/2 views
```

![The window of the session: the rows of the two stages on the left, and on
the right a list of plans that shows walk, above the plan widget of walk:
a list of stages, an input for steps, an input for size and a Run
button](images/plan-controls.png)

The view on the right starts with the list of the plans, which holds `walk`
alone for now. Below it is the plan widget of `walk`: a list with the two
stages, an input for `steps` and one for `size` with the defaults you wrote,
and a **Run** button.

## 5. Run the plan

Leave `stage` selected in the list of stages and press **Run**. The view greys
out, the position of `stage` counts up on the left, and the view comes back:
the stage has moved five steps.

## 6. Change the parameters

Choose `fast_stage` in the list of stages, set `steps` to `10` and `size` to
`0.5`, and press **Run** again. This time the position of `fast_stage` counts
up, by half a millimetre at a time.

You did not write any code for the list or the inputs: they follow the
signature of `walk`.

??? example "The whole script"

    ```{.python}
    --8<-- "docs/tutorials/plan_controls.py"
    ```

## What you built

Controls that run a plan on the stage you choose, with the number of steps
and their size you type in. The window shows the stage moving while the plan
runs, and stays usable meanwhile. Any component that offers a plan adds an
entry to the list of the plans, with no change to the presenter or the view
you wrote here.

## Next steps

- [Acquiring images](acquire-images.md) is the next tutorial: it adds a
  camera, and a component that offers a plan to acquire with it.
- [Questions](../explanation/questions.md) explains how a component asks the
  session what it holds.
- [How presenters run plans](../explanation/plans.md) covers plans that run
  until they are stopped, and actions the user takes while they run.
- [How the Qt plan widgets work](../explanation/qt-widgets.md) lists what a
  plan widget can hold.
