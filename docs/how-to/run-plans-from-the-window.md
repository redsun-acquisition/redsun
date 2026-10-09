---
icon: lucide/play
---

# How to run plans from the window

Add the built-in acquisition stack to a session, and you can run plans from
the window. Its presenter runs the plans your components offer, one at a time,
and its view is where you choose a plan, fill its parameters, and run, pause
and stop it.
[ADR 22](../explanation/decisions/0022-a-built-in-acquisition-stack.md)
explains the design.

## Prerequisites

You need components offering plans, which means anything with a `plan_map`
method, as [`HasPlans`][redsun.HasPlans] describes. The Python blocks below are
parts of one script, and the whole script is at the end.

```{.python}
--8<-- "docs/examples/acquisition.py:plans"
```

The presenter gathers the plans of every such component when the session sets
it up. It leaves out, with a warning naming it, a plan whose signature no plan
widget can show.

## Declare it in a session file

Both components are built into `redsun`, under the plugin id `acquisition`:

```yaml
presenters:
  acquisition:
    plugin_name: redsun
    plugin_id: acquisition
views:
  acquisition_view:
    plugin_name: redsun
    plugin_id: acquisition
pairs:
  - [acquisition_view, acquisition]
```

The pairing makes the twelve links between the two. Written out, they are:

??? example "The same links under `wiring`"

    ```yaml
    wiring:
      acquisition_view.sig_launch: acquisition.launch
      acquisition_view.sig_pause: acquisition.pause
      acquisition_view.sig_resume: acquisition.resume
      acquisition_view.sig_stop: acquisition.stop
      acquisition_view.sig_action: acquisition.request_action
      acquisition_view.sig_base_dir: acquisition.set_base_dir
      acquisition.sig_plan_started: acquisition_view.set_started
      acquisition.sig_plan_done: acquisition_view.set_done
      acquisition.sig_plan_failed: acquisition_view.set_failed
      acquisition.sig_progress: acquisition_view.update_progress
      acquisition.sig_action_changed: acquisition_view.update_action
      acquisition.sig_base_dir_changed: acquisition_view.update_base_dir
    ```

## Declare it in Python

In a session class, declare both components and pair them in `wire()`:

```{.python}
--8<-- "docs/examples/acquisition.py:session"
```

## Use the view

![The acquisition view of the example session: the walk plan chosen, the base
directory, the motor to move and the plan's parameters](images/acquisition.png)

- Choose a plan in the list at the top, and the button beside it shows the
  plan's documentation. The plan's parameters, devices and the callbacks to
  attach follow below.
- The Run button, with a play icon, starts the plan. The view shows it
  running once the presenter reports that it started, and the button turns
  into Stop. A plan marked `@continuous(pausable=True)` also has Pause, which
  turns into Resume. The buttons show icons only; pointing at one shows its
  name. See
  [Write a plan that runs until stopped](write-a-continuous-plan.md).
- Run stays disabled while a list of devices the plan needs is empty.
- `Ctrl+R` runs the chosen plan and `Ctrl+.` stops the running one, from
  anywhere in the window; on macOS they are Command-R and Command-period. The
  [`shortcuts`](../reference/session-file.md#shortcuts) section of the
  session file changes them as `acquisition_view.run_plan` and
  `acquisition_view.stop_plan`.
- When a plan raises, its plan widget shows "failed:" and the error until it
  runs again, and the session log holds the full traceback.
- Each run's files are named after its plan. "Choose root..." sets the
  directory runs write under, and "Browse root" opens it in the system's file
  browser.
- The session's [`Settings`][redsun.Settings] keep the plan you chose last,
  under the view's name, and the next session offers it again.

## Share the engine

The presenter owns the session's [`RunEngine`][redsun.engine.RunEngine] and its
[`Deferrals`][redsun.engine.Deferrals], and shares both. Any component that
asks for a `RunEngine` or `Deferrals` in `setup` receives the presenter's own.

```python
class MyController:
    def setup(self, engine: RunEngine, deferrals: Deferrals) -> None:
        self.engine = engine
        self.deferrals = deferrals
```

!!! warning "A second acquisition presenter stops the session from building"

    Two acquisition presenters would both share a `RunEngine`, and the session
    refuses to build. Declare one.

The presenter also passes on the engine's locks. The light view and the light
presenter can take them through a pairing each:

```yaml
pairs:
  - [acquisition, lights_view]
  - [acquisition, lights]
```

The positioner view and presenter take them the same way:

```yaml
pairs:
  - [acquisition, positioner_view]
  - [acquisition, positioner]
```

## Offer actions

A component whose plans wait for the user, through an
[`ActionManager`][redsun.engine.actions.ActionManager] held as `actions`, is a
[`HasActions`][redsun.HasActions]. The presenter passes on the state of every
such component's actions, so their buttons in the plan widget follow them with
no link of their own, and a press reaches the component of the running plan.

## The example in full

??? example "The whole script"

    ```{.python}
    --8<-- "docs/examples/acquisition.py"
    ```
