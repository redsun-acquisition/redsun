---
icon: lucide/wrench
---

# How to set up a development environment

Get a copy of `redsun` you can change and test.

## Clone and install

```bash
git clone https://github.com/redsun-acquisition/redsun.git
cd redsun
uv sync
```

`uv sync` creates `.venv` and installs `redsun` in it, with the `dev`
[dependency group](https://peps.python.org/pep-0735/). Without `uv`:

```bash
pip install -e . --group dev
```

## Install the git hook

Once per clone, so formatting and lint run on every commit:

```bash
uv run prek install
```

See [Run the commit checks](run-commit-checks.md) for what the hook does.

## Check that it works

```bash
uv run tox
```

This runs every check CI runs: lint, type checks against both Qt bindings,
the tests and the docs build. Each one gets its own environment built from
`uv.lock`, so your result matches CI's. [Run tests](run-tests.md) explains
each environment.
