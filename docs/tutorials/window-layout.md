---
icon: lucide/layout-dashboard
---

# Arranging the window

In this tutorial you give the image the middle of the window, and move the
buttons of the stages below it. It continues from
[Scanning a stage with the camera](scan-plan.md).

Each view says where it goes with its
[placement](../explanation/glossary.md#placement). You change two of them,
move a dock by hand, and put it back.

## Before you start

!!! note "What you need"

    The project folder as you left it, and nothing else.

Open `first_session.py`, and add this import below the ones it has:

```python
from redsun.qt import Central
```

## 1. Put the image in the centre

Every view you've written so far is a [`Dock`][redsun.qt.Dock], a panel
against one edge of the window. [`Central`][redsun.qt.Central] is the main
area of the window instead. In the class `ImageView`, change the placement
line to this one, and leave the rest of the class as it is:

```python
placement: Placement = Central()
```

Run the script:

```bash
uv run first_session.py
```

The image now has the middle of the window, with the stages on its left and
the plans on its right.

## 2. Move the stages to the bottom

In the class `StageView`, change the placement line to this one:

```python
placement: Placement = Dock("bottom")
```

Run the script again:

```bash
uv run first_session.py
```

The stages are now below the image. Choose `snap` in the list of the plans
and press **Run**:

![The window of the session: an image of concentric rings in the centre, the
rows of the stages below it and the plan widget of snap on the
right](images/window-layout.png)

## 3. Move a dock by hand

Drag the view of the plans by its title, and drop it on the left edge of the
window. Close the window and run the script again: the plans are on the
left, where you left them.

The window saves where its docks are when you close it, and puts them back
the next time. It does so only while every view asks for the place it asked
for when the window saved, which is why the stages moved at once in step 2.

## 4. Put the docks back

Open the **Window** menu and choose **Reset layout**. The plans go back to
the right, where their placement puts them.

The same menu lists every dock. Close the plans with the button on their
title bar, then choose **plan_view** in the **Window** menu to bring them
back.

??? example "The whole script"

    ```{.python}
    --8<-- "docs/tutorials/window_layout.py"
    ```

## What you built

You arranged the window with the image in its centre, the stages below it
and the plans beside it. Each view starts where its placement says, stays
where you drag it, and goes back with **Reset layout**.

## Next steps

- [Putting a device behind a service](device-service.md) is the next
  tutorial, where you add a stage that lives in a program of its own.
- [How a frontend shows a session on screen](../explanation/frontends.md)
  lists the placements, along with the menus and toolbars.
- [How to save a session](../how-to/save-a-session.md) says what else the
  settings file holds.
