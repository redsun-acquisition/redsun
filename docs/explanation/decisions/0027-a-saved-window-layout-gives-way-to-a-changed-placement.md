# 27. A saved window layout gives way to a changed placement

Date: 2026-10-08

## Status

Accepted

## Context

A Qt session started with `run` saves where the user left the docks, and puts
them back the next time. Qt restores a dock by its name and ignores the
placement its view asks for, so a changed placement showed nothing until the
user deleted the saved layout by hand. All the session could do was log which
docks stayed away from their placements. A dock the user closed with the
button on its title bar came back only through Qt's right-click menu, which
nothing points to.

## Decision

- Next to the layout, the session saves a digest of every view's placement,
  as `window.layout` in the settings file. It restores the layout only while
  the digest matches, or when the file has none, as one written by 0.14 does.
  Otherwise the docks start where their placements say, and the log says why.
- Changing a placement changes the digest, and so does adding or removing a
  view. A view that fails to build counts with the placement its declaration
  holds, so a failure leaves the digest as it was.
- The window the session makes has a Window menu, `WINDOW_MENU`, with a toggle
  for each dock and "Reset layout". Reset layout puts every dock back where it
  was before a saved layout was restored.

Two other options were rejected. Always keeping the saved layout leaves the
surprise in place. A digest of a declared window layout alone would leave it
in every session that declares none.

### Before

```python
class StageView(QWidget):
    placement: Placement = Dock("bottom")  # was Dock("left")
```

The next run puts the stages on the left again, where the saved layout has
them, and logs that they stay there. They move only once `window.state` is
deleted from the settings file.

### After

The same change puts the stages at the bottom on the next run. A dock the user
moved by hand stays where it was left until a placement changes, and
Window -> Reset layout puts it back at any time.

## Consequences

- Adding a view to a session discards the arrangement its user saved, once.
- A `configure_main_view` hook that sets its own menu bar includes
  `WINDOW_MENU` to keep the Window menu.
- A window layout the session declares can build on this digest and on Reset
  layout.
