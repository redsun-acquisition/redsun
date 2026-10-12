---
icon: lucide/arrow-right-left
---

# How to migrate from 0.14

Release 0.15 keeps the sessions of 0.14, so most projects run on it
unchanged. Five of its changes can still stop a project that worked on 0.14,
and this page gives each one with what to write instead. Two more things
still work in 0.15 and are removed in 0.16; they are at the end, so you can
change them while you are here. The [changelog](../reference/changelog.md)
lists everything else the release added.

## A view constructor can't take `placement`

A view's place in the window is now part of how the session declares it, so
the session keeps the keyword `placement` for itself. A view class whose
constructor takes a keyword of that name is refused when the session reads
its declarations: the view is left out and the log says why. Rename the
keyword in your class. Only the constructor is concerned; a class attribute
named `placement` stays what it was, the view's default place.

```python
# 0.14
class MyView(QWidget):
    def __init__(self, name: str, parent: QWidget, placement: str = "left") -> None: ...


# now
class MyView(QWidget):
    def __init__(self, name: str, parent: QWidget, side: str = "left") -> None: ...
```

To put a view somewhere other than its class's default, give `placement`
where you declare it, as
[How to place a view](place-a-view.md#override-a-views-default-placement)
shows.

## `Session.hooks` holds a tuple for each hook point

A [hook point](../explanation/glossary.md#hook-point) now takes several
providers, the objects a session installs there, so `Session.hooks` maps
each point to a tuple of them, in the order they run. In 0.14 it mapped a
point to its one provider, and a point with no provider was not in the
mapping. Every point the session calls is in the mapping now, with an empty
tuple when nothing is installed there.

```python
# 0.14
provider = session.hooks.get(QtHook.CONFIGURE_APPLICATION)
if isinstance(provider, ConfiguresApplication):
    provider.configure_application(app)


# now
for provider in session.hooks[QtHook.CONFIGURE_APPLICATION]:
    provider.configure_application(app)
```

The 0.14 code raises nothing on 0.15, so it has to be found by hand:
`session.hooks.get(...)` now returns a tuple, the check of its type fails,
and the provider is never called.

A frontend that calls its own hook points uses
[`Session.call_hooks`][redsun.Session.call_hooks] instead of the loop,
because it also skips a provider that raises:

```python
self.call_hooks(
    QtHook.CONFIGURE_APPLICATION,
    lambda provider: provider.configure_application(app),
)
```

That skipping is new as well. A provider that cannot be built, or whose
hook raises, is logged and left out, where 0.14 stopped the build. A session
file that sets `strict: true`, which makes any failure stop the build, still
stops on this one, and so does a `create_application` provider that fails.
[Hook points](../reference/hook-points.md) has the whole rule.

## The `pyside` extra installs `pyside6-essentials`

`redsun[pyside]` now installs `pyside6-essentials` instead of the whole
`pyside6`, because `redsun` uses none of the add-on modules and they are two
thirds of the download. A project that imports one of them (`QtCharts`,
`QtMultimedia`, `QtSerialPort`, `QtWebEngine` and others) adds `pyside6` to
its own dependencies.

An environment that `uv` updates in place needs one repair. When `uv sync`
removes `pyside6`, it also deletes files that `pyside6-essentials` shares
with it, and the session then finds no Qt binding. Reinstall the essentials:

```bash
uv sync --reinstall-package pyside6-essentials
# or, with pip
pip install --force-reinstall --no-deps pyside6-essentials
```

## A test can't leave automatic garbage collection on

The fixtures of `redsun.testing` now turn Python's automatic garbage
collection off for the whole test run, because `pyside6` ends the process
when a widget is freed on a background thread. A test that leaves collection
on fails with a message saying so. The usual cause is a test that turns
collection off for itself and always turns it back on at the end, even when
it found it off.

```python
# 0.14
gc.disable()
try:
    ...
finally:
    gc.enable()


# now
found = gc.isenabled()
gc.disable()
try:
    ...
finally:
    if found:
        gc.enable()
```

A test that checks an object in a reference cycle was freed now calls
`gc.collect()` itself, since nothing collects while the test runs.
[How to test a plugin](test-a-plugin.md) describes the fixtures.

## `ColorSchemeMode.glyph` is removed

The colour scheme button shows an icon since this release, so the character
that stood for each mode has no use and
[`ColorSchemeMode`][redsun.qt.ColorSchemeMode] no longer has `glyph`. Code
that showed a mode as text uses the mode's own value, which is `system`,
`light` or `dark`.

```python
# 0.14
label.setText(mode.glyph)

# now
label.setText(mode.value)
```

## Deprecated, removed in 0.16

These two still work in 0.15 and warn with a `DeprecationWarning`.

The first is a view class that answers `placement` from a property. Set
`placement` as a plain class attribute when the place is always the same, or
give it in the declaration when it depends on the session:

```python
# deprecated
class MyView(QWidget):
    @property
    def placement(self) -> Placement:
        return Dock("left")


# now
class MyView(QWidget):
    placement: Placement = Dock("left")
```

The second is `redsun.session.BUILD_STEPS`, the tuple of the steps a
session's build goes through. Use the enumeration
[`BuildStep`][redsun.session.BuildStep]: iterate it for the steps in order,
and take `len(BuildStep)` for their count.

```python
# deprecated
from redsun.session import BUILD_STEPS

# now
from redsun.session import BuildStep
```

## Other changes

- `redsun.aio.run_coro` raises when it is called on the shared loop's own
  thread, where it used to block for good. It also takes any awaitable now.
- The buttons of the built-in views show icons in place of text. Their words
  are the tooltip and the accessible name, so code that found a button by
  its text finds it by one of those.
- The `config_home` fixture of `redsun.testing` applies to every test, so no
  test writes settings into your own folder.
- A saved window layout is skipped once a view's placement changes, and the
  log says so. The docks then start where their placements say.
