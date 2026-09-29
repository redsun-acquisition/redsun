---
icon: lucide/layout-dashboard
---

# Arranging the window

In this tutorial you give the image the middle of the window, and move the
buttons of the stages below it. It continues from
[Scanning a stage with the camera](scan-plan.md).

Each view says where it goes with its
[placement](../explanation/glossary.md#placement). You will change two of
them, and find out what the window remembers between two runs.

## Before you start

!!! note "What you need"

    The project folder as you left it, and nothing else.

Open `first_session.py`, and add this import below the ones it has:

```python
from redsun.qt import Central
```

## 1. Put the image in the centre

Every view you wrote so far is a [`Dock`][redsun.qt.Dock]: a panel against
one edge of the window. [`Central`][redsun.qt.Central] is the main area of
the window. In the class `ImageView`, change the line of the placement to
this one, and leave the rest of the class as it is:

```python
placement: Placement = Central()
```

Run the script:

```bash
uv run first_session.py
```

The image has the middle of the window, with the stages on its left and the
plans on its right.

## 2. Move the stages to the bottom

In the class `StageView`, change the line of the placement to this one:

```python
placement: Placement = Dock("bottom")
```

Run the script again. The stages are still on the left.

Nothing is wrong with the line. The window saves where its docks are when
you close it, and puts them back the next time. A placement says where a
view goes when the window has nothing saved for it. The image moved at once
in step 1 because it stopped being a dock, and the window saves where its
docks are.

## 3. Forget the saved layout

The window keeps its layout in one file, named after the session. Close the
window and delete the file:

| Platform | File |
| --- | --- |
| Windows | `%LOCALAPPDATA%\redsun\first-session.json` |
| macOS | `~/Library/Application Support/redsun/first-session.json` |
| Linux | `~/.config/redsun/first-session.json` |

Run the script once more:

```bash
uv run first_session.py
```

The stages are below the image. Choose `snap` in the list of the plans and
press **Run**:

![The window of the session: an image of concentric rings in the centre, the
rows of the stages below it and the plan widget of snap on the
right](images/window-layout.png)

## 4. Move a dock by hand

Drag the view of the plans by its title, and drop it on the left edge of the
window. Close the window, and run the script again: the plans are on the
left, where you left them.

??? example "The whole script"

    ```{.python}
    --8<-- "docs/tutorials/window_layout.py"
    ```

## What you built

A window with the image in its centre, the stages below it and the plans
beside it. Each view starts where its placement says, and stays where you
drag it.

## Next steps

- [Putting a device behind a service](device-service.md) is the next
  tutorial: it adds a stage that lives in a program of its own.
- [How a frontend shows a session on screen](../explanation/frontends.md)
  lists the placements, menus and toolbars included.
- [How to save a session](../how-to/save-a-session.md) says what else the
  file of step 3 holds.
