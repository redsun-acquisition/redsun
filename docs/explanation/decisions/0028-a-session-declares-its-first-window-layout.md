# 28. A session declares its first window layout

Date: 2026-10-09

## Status

Accepted

## Context

A view chooses where it goes with its placement: an edge of the window, or
the centre, and a group to share tabs with. That is enough for a few views,
but a window with twenty docks needs more. It has to say which views sit side
by side, which share tabs, how wide an edge is and which views start hidden.
A view can't say any of that, because a view from a plugin doesn't know the
other views of the application it ends up in.

## Decision

- The session declares the first layout of its window, because the session
  is the one that knows every view. It does so in the method
  `window_layout()`, or in a `layout:` section of the session file. The file
  replaces what the method returns, whole, and a later file replaces an
  earlier one whole, since two layout trees have no single obvious merge.
- A layout fills regions with view names, rows, columns and tabs. Tabs hold
  view names only, because a dock can only be tabbed with another dock.
- A view the layout leaves out goes where its placement asks, groups
  included. So a session that declares no layout gets the window it got
  before.
- The frontend lists its regions in `Frontend.regions`, and for each one how
  a view the layout leaves out joins it: stacked, side by side or as a tab.
  `Frontend.region_of` says which region each placement asks for, and
  `Frontend.hides` whether the frontend can start a view hidden. A layout the
  frontend can't show is refused when the configuration is read, before
  anything is built.
- A name no view answers to is logged and left out, and refused under
  `strict`.
- Sizes are shares of the window, never pixels, because pixels are wrong on
  another screen. They apply once the window shows. A saved layout keeps the
  sizes the user left, and **Reset layout** gives the declared ones back.
- The Qt session also saves where the user left the centre's splitters and
  tabs, as `window.center`.

Other options were rejected:

- Tab groups only. A large window also needs rows and sizes.
- The view alone deciding. A view from a plugin couldn't sit in different
  groups in different applications.
- The session alone deciding. A view couldn't suggest a group when the
  session declares no layout.
- Merging layout trees across files, for the reason above.
- `Split` and `Layout` as names. `Split` doesn't say which way it splits, and
  `Layout` clashes with Qt's `QLayout`.
- The types in `redsun.qt`. A second frontend would need its own copies.

### Before

```python
class StageView(QWidget):
    placement: Placement = Dock("right")


class LightView(QWidget):
    placement: Placement = Dock("right")


class CameraView(QWidget):
    placement: Placement = Dock("right")
```

The three views stack on the right edge, one above the other, and nothing
says the stages should take less room than the other two.

### After

```python
class MyApp(QtSession):
    stage: AsView[StageView]
    lights: AsView[LightView]
    camera: AsView[CameraView]

    def window_layout(self) -> WindowLayout | None:
        return WindowLayout(
            regions={"right": Column("stage", Tabs("lights", "camera"), sizes=(1, 2))},
            sizes={"right": 0.3},
        )
```

The stages sit above the lights and the camera, which share tabs, and take a
third of the edge. The edge takes 30% of the window's width.

## Consequences

- The window keeps a saved arrangement only while the layout it would build
  is the one it was saved with, as
  [ADR 27](0027-a-saved-window-layout-gives-way-to-a-changed-placement.md)
  decided. That check now covers the whole layout, the declared part
  included, so an arrangement saved by an earlier 0.15 development build is
  skipped once.
- A group of docks shows its first view on top. Qt showed the last one.
- Another frontend can show layouts too, by filling in `regions`, `hides`
  and `region_of`.
