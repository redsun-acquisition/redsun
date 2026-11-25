---
icon: lucide/arrow-right-left
---

# How to migrate from 0.18

Release 0.19 makes the example session a command of `redsun`, where 0.18
had an option for it. This page gives the change your scripts or your notes
may need. The [changelog](../reference/changelog.md) lists everything else
the release changed.

## The example is a command

The [`redsun` command](../reference/command-line.md) now takes commands, and
opening the example session is the first of them. The option `--example` is
gone, so write `example` in its place, with the style after it as before:

```bash
# 0.18
redsun --example
redsun --example napari

# now
redsun example
redsun example napari
```

`redsun --version` is unchanged, and `redsun` with nothing after it still
prints the help, which now lists the commands.
