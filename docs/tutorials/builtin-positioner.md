---
icon: lucide/move
---

# Reusing the built-in positioner

Sometimes you don't need to write a presenter or a view yourself, because
`redsun` already offers one. In this tutorial you replace the nudge presenter
and view of your session with the positioner `redsun` ships. It's a
[stack](../explanation/glossary.md#stack) (a presenter and a view written to
work together) that steps, moves and stops any stage, and saves positions to
go back to. It continues from
[Putting a device behind a service](device-service.md).

## Before you start

!!! note "What you need"

    The project folder of [Putting a device behind a service](device-service.md),
    with `first_session.py`, `stage_ioc.py` and `session.yaml`.

The positioner works with any device that `ophyd-async` can move and that
reports its position as it changes. Your three stages already qualify, so you
don't change any of them. Since [Writing your first session](first-session.md),
each one has been a `StandardMovable`, which gives it the `set`, `locate`,
`stop` and `subscribe` methods the positioner uses. The positioner replaces the
nudge presenter and view, and nothing else in the session.

Open `first_session.py`, and add these imports below the ones it has:

```python
from redsun.presenter import PositionerPresenter
from redsun.view.qt.builtins import PositionerView
```

## 1. Remove the nudge presenter and view

Delete the classes `StagePresenter` and `StageView`. In the session, delete
the lines that declare `stage_ctrl` and `stage_view`, and the four links that
use them:

```python
yield self.stage_view.sig_nudge, self.stage_ctrl.nudge
yield self.stage.position, self.stage_view.show_reading
yield self.fast_stage.position, self.stage_view.show_reading
yield self.remote_stage.position, self.stage_view.show_reading
```

That leaves three imports unused, `Reading`, `QFormLayout` and
`QPushButton`, so delete them as well.

## 2. Declare the positioner

The positioner's view docks on the right of the window, where the plan
controls already are. Since a view's class sets where it sits, the one thing
you write is a subclass that changes only its `placement`, to the left of the
window, which is free. Add it below `ScanPlans`:

```{.python}
--8<-- "docs/tutorials/builtin_positioner.py:view"
```

Add the presenter and your view to the session, below `scan_plans`:

```{.python}
--8<-- "docs/tutorials/builtin_positioner.py:declare"
```

The presenter receives every device of the session, as `StagePresenter`
did, and keeps the ones it can move: the three stages, but not the camera.
When the session sets the view up, the view asks the presenter which stages
and axes there are, so it needs no list of its own.

## 3. Wire it

Add these links at the start of `wire`:

```{.python}
--8<-- "docs/tutorials/builtin_positioner.py:wire"
```

The first four send what the user does to the presenter: a step, a move to a
typed position, a stop, or a change of configuration. The others send back
what the stages do: where they are, whether they're moving, why a move
failed, their limits and their configuration. These links are the same in
every session that uses the positioner, and
[Move devices by hand](../how-to/move-devices-by-hand.md) lists them as well.
Because the presenter and the view were written for each other, one line,
`yield from links_between(self.positioner_view, self.positioner)`, makes the
same links; [How to offer a pairing](../how-to/offer-a-pairing.md) explains
how.

## 4. Change the session file

`session.yaml` still gives a `step` to `stage_ctrl`, which the session no
longer declares. The session would report that entry as a component it failed
to build, so replace it. The positioner offers a choice of step sizes beside
each stage, and the file can say which sizes to offer:

```yaml
session: first-session

views:
  positioner_view:
    steps: [0.1, 0.5, 1.0]
```

## 5. Run it

Start the session:

```bash
uv run first_session.py
```

```text
Service 'stage_ioc' started
Services started: 1/1
Session built: 4/4 devices, 5/5 presenters, 3/3 views
```

![The window with the positioner docked on the left, a group for each of the
three stages, the plan controls on the right](images/builtin-positioner.png)

Compare it with the window of the
[last tutorial](device-service.md#4-run-it): the row of nudge buttons at the
bottom is gone, and the positioner on the left has a group for each of
`stage`, `fast_stage` and `remote_stage`. Each group shows where its stage
is, minus and plus buttons with a step size beside them, and a field where
you type a position to go to. Hold the plus button, and the stage keeps
stepping until you let go. Pointing at a button shows its name.

The Save button records where a stage stands in the Saved positions
section, under a name you can change, and the Go button beside the saved
entry moves the stage back
there. The Advanced tab sets how fast a held button repeats. The
Configuration tab lists the configuration a stage declares; yours declare
none, so the tab says so.

??? example "The whole script"

    This script reads its session file from `builtin_positioner.yaml`, so
    that the scripts of the earlier tutorials keep theirs. Yours reads
    `session.yaml`.

    ```{.python}
    --8<-- "docs/tutorials/builtin_positioner.py"
    ```

## What you built

You replaced the nudge presenter and view of your session with the
positioner `redsun` ships. You declared and wired its presenter and view, but
didn't write them, apart from the line that says where the view sits.

## Next steps

- [Move devices by hand](../how-to/move-devices-by-hand.md) covers the
  positioner's options, and how to change its behaviour in a subclass.
- [Write a component](../how-to/write-a-component.md) is the place to start
  when no built-in component does what you need.
