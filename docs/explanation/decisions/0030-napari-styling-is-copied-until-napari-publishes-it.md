# 30. napari's styling is copied until napari publishes it

Date: 2026-10-09

## Status

Accepted

## Context

A Qt session used the style the platform gives every window, and the only
way to change its look was to write a `configure_application`
[hook](../glossary.md#hook) provider. Many labs run `napari` beside their
acquisition software, and two windows that look alike are easier to move
between. napari's styling is three Qt stylesheets with placeholders, a set
of SVG icons recoloured for each theme, and the Python that fills them in.
It ships only
inside `napari` itself, which is far too large a dependency for a look.
napari plans to publish its styling as a package of its own, but that
package doesn't exist yet.

A session file also had no short way to name a provider `redsun` ships: it
had to spell out the class path.

## Decision

- `redsun` copies napari 0.9.2's stylesheets and icons unchanged, with
  napari's BSD 3-Clause licence, and rewrites the code that fills them in.
  The result matches napari's own output for both themes.
- `NapariStyle` in `redsun.qt.styles.napari` is a `configure_application`
  provider. It picks napari's dark or light theme from the colour scheme,
  and picks again whenever the scheme changes, so the colour scheme button
  stays the one switch. At shutdown it puts back the stylesheet the
  application had before.
- `redsun`'s own manifest gets a `hooks` section of short names. A session
  file names a built-in provider as `configure_application: napari`, or as
  `provider: napari` when it passes `kwargs`.
- The stylesheet points at the recoloured icons by their file path. napari
  registers the folder under a path prefix such as `theme_dark` with
  `QDir.addSearchPath`, which adds the folder once more at every call, and
  `QDir.setSearchPaths`, which would replace it, refuses a prefix holding an
  underscore. A file path needs neither, and leaves behind no setting that
  every window in the process shares.
- `redsun.qt.styles` imports nothing, so a session loads only the style it
  names.

### Before

```python
class NapariLike:
    def configure_application(self, app: QApplication) -> None:
        app.setStyleSheet(Path("napari-dark.qss").read_text())


class MyApp(QtSession):
    configure_application: AsHook[NapariLike]
```

The stylesheet is copied by hand, its images don't load, and it stays dark
whatever the colour scheme button says.

### After

```yaml
hooks:
  configure_application: napari
```

Other options were rejected:

- Depending on `napari`. It installs a viewer, its plugins and their
  dependencies to style one window.
- One `redsun.qt.styles` module importing every style. A session would
  import the dependencies of styles it doesn't use.
- Styles as factory functions or modules. The hook loader takes a class, and
  a style keeps the application and its connection to the scheme, which
  belong to one object per session.
- napari's icons for the built-in views. They have no pause, save or target
  icon, so the views would need two icon sources kept in step.

## Consequences

- When napari publishes its styling as a package, `redsun` depends on it and
  deletes the copy.
- A second style, built on `qlementine`, follows the same pattern: a module
  under `redsun.qt.styles` and a short name in the manifest.
- A style and the built-in views' icons stay independent: the icons take
  the window's text colour, which every style sets.
