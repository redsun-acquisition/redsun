---
icon: lucide/share-2
---

# How to share a value between components

When one component makes something that others need, such as a viewer model, a
calibration or the readings of a motor, you share it as a
[shared value](../explanation/glossary.md#shared-value), named by its type.

## Share it

Mark a method with [`provides`][redsun.provides]. Its return type is what
others ask for:

```python
from qtpy.QtWidgets import QWidget

from redsun import provides


class Canvas:
    """The area an image view draws on."""


class ImageView(QWidget):
    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self._canvas = Canvas()

    @provides
    def canvas(self) -> Canvas:
        return self._canvas
```

The session calls the method once, right after it makes the component, and
gives every component that asks the same object. So return something the
constructor already made, because a value `setup` assigns later doesn't exist
yet.

## Ask for it

Ask in `setup`, by type:

```python
class RoiView(QWidget):
    def setup(self, canvas: Canvas) -> None:
        self._canvas = canvas
```

Every component exists when `setup` runs, so it doesn't matter which one is
declared first. If nothing shares a `Canvas`, the session doesn't start and
names `RoiView` and the type.

A component can only ask for what its own
[layer](../explanation/glossary.md#layer) or an earlier one shares, so the
session refuses a presenter that asks for something only a view shares.

## Make it optional

Give the parameter `| None` and a default of `None`:

```python
def setup(self, overlay: Overlay | None = None) -> None:
    self._overlay = overlay
```

If a component in the session shares an `Overlay`, you get it. If none does,
you get `None`.

## Share a value no component owns

A value that belongs to no component, such as a calibration loaded from a file,
comes from a [provider](../explanation/glossary.md#provider). A provider is an
ordinary class whose `provides` methods share values before any component is
made.

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

- The type is the key. Two components can't share the same type, so give
  distinct values distinct types.
- A `provides` method returning `X | None` doesn't make an optional `X`. See
  [Limitations](../explanation/limits.md#can-a-shared-value-be-optional).
- Import the type normally, not under `if TYPE_CHECKING:`, since the session
  reads it while running.
