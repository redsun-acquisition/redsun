---
icon: lucide/download
---

# Installation

In this tutorial you make a project folder and install `redsun` in it. The
tutorials that follow are written in that folder.

## Before you start

!!! note "What you need"

    [`uv`](https://docs.astral.sh/uv/), which makes the project, installs the
    packages and runs the scripts. Its documentation shows [how to install
    it](https://docs.astral.sh/uv/getting-started/installation/). You do not
    need to install Python: `uv` fetches it.

## 1. Make the project

Open a terminal in the place where you keep your work, and make a project
called `my-microscope`:

```bash
uv init --bare --pin-python --python 3.12 my-microscope
```

```text
Initialized project `my-microscope` at `/home/you/my-microscope`
```

The folder holds two files. `pyproject.toml` lists what the project needs,
and `.python-version` says which Python runs it.

Go into the folder. Every command of the tutorials is run from there:

```bash
cd my-microscope
```

## 2. Install redsun

Add `redsun` to the project, with
[PyQt6](../explanation/glossary.md#qt-binding) to draw its windows:

```bash
uv add "redsun[pyqt]"
```

`uv` makes a virtual environment in the folder, called `.venv`, and installs
`redsun` in it. You never activate that environment: `uv run` uses it.

## 3. Check that it works

```bash
uv run python -c "import redsun; print(redsun.__version__)"
```

It prints the version that was installed:

```text
0.14.0
```

## What you built

A project folder, `my-microscope`, with `redsun` and PyQt6 installed in an
environment of its own.

## Next steps

- [Writing your first session](first-session.md) is the next tutorial: a
  window with a button that moves a stage.
- [How to install redsun](../how-to/install-redsun.md) covers other tools,
  the other Qt binding, and the extras for storing data.
