---
icon: lucide/palette
---

# How to choose a style

A Qt session looks like the other programs on your computer, because it uses
the style your platform gives every window. You can give it the look of
`napari` instead, an image viewer many labs already use, so the two programs
look alike side by side. The style comes with `redsun`, and you turn it on
with one line.

![The positioner view in napari's dark theme](images/napari-style.png)

## Prerequisites

You need a [`QtSession`][redsun.qt.QtSession]. The style is a
[hook](../explanation/glossary.md#hook) provider, so
[How to install hooks](install-hooks.md) explains the two ways of installing
it shown below.

## Turn on the style

Install `NapariStyle` at the `configure_application` hook point:

=== "Session class"

    ```{.python}
    --8<-- "docs/examples/napari_style.py:hook"
    ```

    Import it from `redsun.qt.styles.napari`.

=== "Session file"

    ```yaml
    hooks:
      configure_application: napari
    ```

    `napari` is the short name of the style, so you don't write its class
    path.

The window then takes napari's colours and font sizes, and napari's own
pictures for check boxes, arrows and other small controls. The buttons of the
built-in views keep `redsun`'s own icons, which take the theme's text colour,
so they are light in the dark theme and dark in the light one.

## Switch between dark and light

The style follows the session's colour scheme, so it has a dark and a light
theme and needs no setting of its own. The colour scheme button on the
toolbar switches between them while the session runs, and the
[`color_scheme`](save-a-session.md#choose-the-colour-scheme) key of the
session file chooses where it starts. When the scheme is `system` and your
platform doesn't say which it prefers, the style uses the light theme.

## Undo the style

The style keeps the stylesheet the application had before. When the session
shuts down, the style puts it back and stops following the colour scheme.

## Where the files come from

The stylesheets and icons are napari 0.9.2's, copied unchanged into
`redsun.qt.styles`, so napari doesn't need to be installed. They stay under
napari's BSD 3-Clause licence, which is beside them. The style writes the
icons in the theme's colours to your user cache folder the first time it
needs them, and reuses them after that.

## See also

- [How to install hooks](install-hooks.md) shows how to write a style of
  your own, as a `configure_application` provider.
- [ADR 30](../explanation/decisions/0030-napari-styling-is-copied-until-napari-publishes-it.md)
  records why the files are copied.

## The example in full

??? example "The whole script"

    ```{.python}
    --8<-- "docs/examples/napari_style.py"
    ```
