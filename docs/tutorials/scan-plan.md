---
icon: lucide/scan-line
---

# Scanning a stage with the camera

In this tutorial you add a plan that uses two devices at once: it moves a
stage, and takes a frame with the camera at each position. It continues from
[Acquiring images](acquire-images.md).

The plan lives in a presenter that holds nothing else: no `RunEngine`, no
signal, no view. You write that one class and one line of the session, and
the window offers the scan.

## Before you start

!!! note "What you need"

    The project folder as you left it, and nothing else. The file needs no
    new import either.

## 1. Write the presenter

Open `first_session.py`, and add a presenter below `ImageView`:

```{.python}
--8<-- "docs/tutorials/scan_plan.py:scan_plans"
```

`scan` wraps a plan `bluesky` already has, also called
[`scan`][bluesky.plans.scan]. It moves through `points` positions from
`start` to `stop`, and reads the camera at each one.

The plan asks for a stage and a camera through the two protocols you wrote,
`HasPosition` and `Camera`. It names no device, and the presenter holds none.

## 2. Add it to the session

Add the highlighted line:

```{.python hl_lines="10"}
--8<-- "docs/tutorials/scan_plan.py:session"
```

`wire` does not change. Run the script:

```bash
uv run first_session.py
```

```text
Container built: 3/3 devices, 5/5 presenters, 3/3 views
```

The list of the plans has a third entry, `scan`.

## 3. Run the scan

Choose `scan` in the list of the plans. Its plan widget has two lists, one
for the stage and one for the camera, and an input for `start`, `stop` and
`points`:

![The window of the session: the rows of the stages on the left, and on the
right the plan widget of scan, with a list of stages, a list of cameras and
three inputs, above an image of concentric
rings](images/scan-plan.png)

Press **Run**. The position of `stage` goes from `0.0` to `5.0`, one
millimetre at a time, and the last frame appears below.

## 4. Find the file

Open the folder of the camera, where the last tutorial left its files. It
has a new one, `scan_00000.h5`, named after the plan. It holds six frames,
one for each position.

To count them, run this command with the path of the file in the place of
the last word:

```bash
uv run python -c "import h5py, sys; print(h5py.File(sys.argv[1])['entry/data/data'].shape)" PATH
```

```text
(6, 240, 320)
```

The file holds the frames and not the positions. The positions are in the
documents of the run, and nothing in this session keeps them.
[How to keep a catalog of runs](../how-to/keep-a-catalog.md) does.

## 5. Scan the other stage

Choose `fast_stage` in the list of stages, set `points` to `3`, and press
**Run**. `fast_stage` goes to `0.0`, then to `2.5` and to `5.0`, and
`scan_00001.h5` holds three frames.

??? example "The whole script"

    ```{.python}
    --8<-- "docs/tutorials/scan_plan.py"
    ```

## What you built

A scan that moves the stage you choose and takes a frame at each position,
in one file for each run.

You put it together from parts that do not name each other. The stage and
the camera reach the plan through two protocols. The plan reaches the
presenter that runs it, and the view that shows its plan widget, because its
presenter offers plans. The frames reach the presenter that shows them
through the documents of the run. Each part can be replaced, or taken to
another session, without editing the others.

## Next steps

- [Arranging the window](window-layout.md) is the next tutorial: it gives the
  image the middle of the window.
- [How presenters run plans](../explanation/plans.md) covers plans that run
  until they are stopped, and actions the user takes while they run.
- [Questions](../explanation/questions.md) explains how a component asks the
  session what it holds.
