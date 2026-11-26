---
icon: lucide/arrow-right-left
---

# How to migrate from 0.18

Release 0.19 changes how you open the example session from a terminal. This
page gives the change your scripts or your notes may need. The
[changelog](../reference/changelog.md) lists everything else the release
changed.

## The example is a subcommand

The [`redsun` command](../reference/command-line.md) now takes a subcommand
that says what it should do, and opening the example session is the first of
them. The option `--example` is gone, so write
`example` in its place, with the [style](choose-a-style.md) after it as
before:

```bash
# 0.18
redsun --example
redsun --example napari

# now
redsun example
redsun example napari
```

`redsun --version` is unchanged, and `redsun` with nothing after it still
prints the help, which now lists the subcommands.
