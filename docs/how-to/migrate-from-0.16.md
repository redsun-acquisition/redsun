---
icon: lucide/arrow-right-left
---

# How to migrate from 0.16

Release 0.17 moves to `bluesky` 1.16, which renames the method a device
uses to report new readings. This page gives the one change your code may
need. The [changelog](../reference/changelog.md) lists everything else the
release changed.

## An axis reports readings through `subscribe_reading`

The positioner follows an [`Axis`][redsun.utils.devices.Axis] by calling its
`subscribe_reading` method, the name `bluesky` 1.16 gives it, instead of
`subscribe`. An axis built on `ophyd-async`, such as a `StandardMovable` or a
signal, has both methods and needs no change. An axis you wrote by hand with
only `subscribe` is no longer an `Axis`, so the positioner leaves it out.
Rename the method:

```python
# 0.16
class MyAxis(StandardReadable):
    def subscribe(self, function: Callback[float]) -> None:
        self.position.subscribe_reading(function)


# now
class MyAxis(StandardReadable):
    def subscribe_reading(self, function: Callback[float]) -> None:
        self.position.subscribe_reading(function)
```
