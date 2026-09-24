---
icon: lucide/share-2
---

# How to share a value between components

One component makes something, and others need it: a viewer model, a
calibration, the readings of a motor. Share it as a
[shared value](../reference/glossary.md#shared-value), named by its type.

## Share it

Mark a method with [`provides`][redsun.provides]. Its return type is what
others ask for:

```python
from redsun import provides


class ImageView(QWidget):
    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self._viewer = ViewerModel()

    @provides
    def viewer(self) -> ViewerModel:
        return self._viewer
```

The session calls the method once, right after it makes the component, and
gives every component that asks the same object. So return something the
constructor already made: a value `setup` assigns later does not exist yet.

## Ask for it

Ask in `setup`, by type:

```python
class RoiView(QWidget):
    def setup(self, viewer: ViewerModel) -> None:
        self._viewer = viewer
```

Every component exists when `setup` runs, so it does not matter which one is
declared first. If nothing shares a `ViewerModel`, the session does not start
and names `RoiView` and the type.

A component may only ask for what its own [layer](../reference/glossary.md#layer)
or an earlier one shares. A presenter asking for something only a view shares
is refused.

## Make it optional

Give the parameter `| None` and a default of `None`:

```python
def setup(self, overlay: Overlay | None = None) -> None:
    self._overlay = overlay
```

If a component in the session shares an `Overlay`, you get it. If none does,
you get `None`.

## Share a value no component owns

A value that belongs to no component, such as a calibration loaded from a
file, comes from a provider: an ordinary class whose `provides` methods share
values before any component is made.

```python
from redsun import SessionConfig, provides


class Calibrations:
    def __init__(self, config: SessionConfig) -> None:
        self._session = config.session

    @provides
    def calibration(self) -> Calibration:
        return Calibration.load(self._session)
```

List it on the session class:

```python
class MyApp(QtSession):
    providers = [Calibrations]
```

or, from a plugin, in the session file:

```yaml
providers:
  calibrations:
    plugin_name: my-plugin
    plugin_id: calibrations
```

## Rules to know

- The type is the key. Two components sharing the same type is an error, so
  give distinct values distinct types.
- A `provides` method returning `X | None` does not make an optional `X`. See
  [Limits](../explanation/limits.md#a-shared-value-cannot-be-optional).
- Import the type normally, not under `if TYPE_CHECKING:`, since the session
  reads it while running.
