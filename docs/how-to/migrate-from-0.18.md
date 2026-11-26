---
icon: lucide/arrow-right-left
---

# How to migrate from 0.18

Release 0.19 refuses an `async` slot on a Qt view. This page gives the change
your code may need. The [changelog](../reference/changelog.md) lists
everything else the release changed.

## A Qt view's slot is a plain `def`

The Qt frontend runs a view's slots on the GUI thread, which is the only
thread allowed to touch a widget, so it now refuses a view that marks an
`async def` method with `slot`. The session logs the declaration, naming the
slot, and runs without that view. Before, the view was accepted and the slot
ran as a coroutine on the session's loop, off the GUI thread. Write the slot as
a plain `def`:

```python
# 0.18: accepted, then touched the widget from the wrong thread
class MyView(QWidget):
    @slot
    async def show_position(self, position: float) -> None:
        self.label.setText(str(position))


# 0.19
class MyView(QWidget):
    @slot
    def show_position(self, position: float) -> None:
        self.label.setText(str(position))
```

A frontend decides whether its views may have `async` slots through
[`Frontend.async_view_slots`][redsun.Frontend.async_view_slots], and no
frontend `redsun` ships sets it.
