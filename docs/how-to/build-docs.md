# Build documentation

This guide covers how to build the Redsun documentation locally.

## Prerequisites

Make sure you have [installed `redsun` with development dependencies](installation.md#install-development-dependencies).

## Build with Zensical

Build the documentation from the project root:

```bash
uv run tox -e docs
```

That builds the site and then runs `scripts/check_xrefs.py`, which reports any
cross-reference that resolves to nothing. A green `zensical build` does not
catch those on its own, so run the environment rather than the build alone:

```bash
uv run zensical build          # build only, no cross-reference check
```

The built documentation lands in the `site/` directory. Serve it locally with:

```bash
uv run zensical serve
```

This starts a local server at `http://localhost:8000` and automatically rebuilds when you make changes.

## Troubleshooting

### Missing dependencies

If you get errors about missing dependencies:

```bash
uv sync --group docs
```

`uv run tox -e docs` installs them itself, from `uv.lock`.

### Port already in use

If port 8000 is already in use, specify a different port:

```bash
uv run zensical serve --dev-addr localhost:8080
```

## Next steps

- Learn how to [run tests](run-tests.md)
- Read about [Redsun's architecture](../explanation/container-architecture.md)
